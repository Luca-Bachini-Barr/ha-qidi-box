"""Box actions: load, unload, eject, set a slot's filament, and raw G-code."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .api import MoonrakerError
from .const import (
    ATTR_COLOR,
    ATTR_DEVICE_ID,
    ATTR_FILAMENT,
    ATTR_GCODE,
    ATTR_SLOT,
    ATTR_VENDOR,
    ATTR_WAIT,
    COMMAND_FAST_POLL_SECONDS,
    CONF_MOONRAKER_ENTRY_ID,
    DOMAIN,
    GCODE_ACCEPT_TIMEOUT,
    MAX_SLOT,
    MOONRAKER_DOMAIN,
    SERVICE_EJECT,
    SERVICE_LOAD,
    SERVICE_SEND_GCODE,
    SERVICE_SET_SLOT_FILAMENT,
    SERVICE_UNLOAD,
)

if TYPE_CHECKING:
    from .coordinator import QidiBoxCoordinator

_LOGGER = logging.getLogger(__name__)

_SLOT = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_SLOT))
# Values go into G-code between single quotes
_QUOTABLE = vol.All(cv.string, vol.Match(r"^[^'\n\r]+$"))
_HEX = vol.All(cv.string, vol.Match(r"^#?[0-9A-Fa-f]{6}$"))

SEND_GCODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_GCODE): vol.Any(cv.string, [cv.string]),
        vol.Optional(ATTR_WAIT, default=True): cv.boolean,
    }
)
SLOT_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string, vol.Required(ATTR_SLOT): _SLOT}
)
SET_SLOT_SCHEMA = SLOT_SCHEMA.extend(
    {
        vol.Required(ATTR_COLOR): _HEX,
        vol.Required(ATTR_VENDOR): _QUOTABLE,
        vol.Required(ATTR_FILAMENT): _QUOTABLE,
    }
)

# The touchscreen's own commands (captured from Moonraker's gcode_store); a flow
# heats, cuts, unloads and loads, and takes about 2.5 minutes.
SLOT_COMMANDS = {
    SERVICE_LOAD: "LOAD_FILAMENT_CONTROL",
    SERVICE_UNLOAD: "UNLOAD_FILAMENT_CONTROL",
    SERVICE_EJECT: "EJECT_FILAMENT_CONTROL",
}


def coordinator_for_device(hass: HomeAssistant, device_id: str) -> QidiBoxCoordinator:
    """Return the Box coordinator of a printer device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Unknown device {device_id}")
    moonraker_ids = {
        identifier
        for domain, identifier in device.identifiers
        if domain == MOONRAKER_DOMAIN
    }
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_MOONRAKER_ENTRY_ID) in moonraker_ids:
            if entry.state is not ConfigEntryState.LOADED:
                raise HomeAssistantError(f"QIDI Box {entry.title} is not loaded")
            return entry.runtime_data
    raise ServiceValidationError(
        f"{device.name_by_user or device.name} has no QIDI Box"
    )


async def async_send(
    coordinator: QidiBoxCoordinator, script: str, *, wait: bool
) -> None:
    """Run a G-code script on the printer.

    With ``wait`` false the call returns once Klipper has had a few seconds to
    reject the script; a filament change runs for minutes, longer than a
    dashboard should wait. Errors that come later are logged.
    """
    hass = coordinator.hass
    task = hass.async_create_background_task(
        coordinator.client.gcode(script), f"{DOMAIN} gcode {script[:40]}"
    )
    hass.async_create_task(coordinator.async_poll_fast_for(COMMAND_FAST_POLL_SECONDS))
    if not wait:
        done, _ = await asyncio.wait({task}, timeout=GCODE_ACCEPT_TIMEOUT)
        if not done:
            task.add_done_callback(lambda t, s=script: _log_late_result(t, s))
            return
    try:
        await task
    except MoonrakerError as err:
        raise HomeAssistantError(f"Klipper: {err}") from err


def _log_late_result(task: asyncio.Task, script: str) -> None:
    if task.cancelled():
        return
    if (err := task.exception()) is not None:
        _LOGGER.warning("G-code %r failed: %s", script, err)
    else:
        _LOGGER.debug("G-code %r finished", script)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Box actions."""

    async def send_gcode(call: ServiceCall) -> None:
        gcode = call.data[ATTR_GCODE]
        script = (
            "\n".join(line for line in gcode if line)
            if isinstance(gcode, list)
            else gcode
        )
        if not script.strip():
            raise ServiceValidationError("Empty G-code")
        coordinator = coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        await async_send(coordinator, script, wait=call.data[ATTR_WAIT])

    async def slot_command(call: ServiceCall) -> None:
        coordinator = coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        command = SLOT_COMMANDS[call.service]
        await async_send(
            coordinator, f"{command} SLOT={call.data[ATTR_SLOT] - 1}", wait=False
        )

    async def set_slot_filament(call: ServiceCall) -> None:
        coordinator = coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        color = re.sub(r"^#", "", call.data[ATTR_COLOR]).upper()
        await async_send(
            coordinator,
            f"UPDATE_FILAMENT_INFORMATION SLOT={call.data[ATTR_SLOT] - 1} "
            f"COLOR='{color}' VENDOR='{call.data[ATTR_VENDOR]}' "
            f"FILAMENT='{call.data[ATTR_FILAMENT]}'",
            wait=True,
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_GCODE, send_gcode, SEND_GCODE_SCHEMA
    )
    for service in SLOT_COMMANDS:
        hass.services.async_register(DOMAIN, service, slot_command, SLOT_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SLOT_FILAMENT, set_slot_filament, SET_SLOT_SCHEMA
    )
