"""QIDI Box for Moonraker.

Adds the QIDI Box (multi-filament feeder) to the printer device of the
Moonraker integration: slot filament sensors, drying, filament change and
warnings, the Box heater target, and actions to load, unload and eject
filament. It reads the printer's address from the Moonraker config entry and
talks to Moonraker itself.
"""

from __future__ import annotations

from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
    ConfigEntryState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import MoonrakerClient, MoonrakerError
from .const import (
    CONF_MOONRAKER_ENTRY_ID,
    DOMAIN,
    MOONRAKER_CONF_API_KEY,
    MOONRAKER_CONF_PORT,
    MOONRAKER_CONF_TLS,
    MOONRAKER_CONF_URL,
    MOONRAKER_DEFAULT_PORT,
    MOONRAKER_DOMAIN,
    PLATFORMS,
)
from .coordinator import QidiBoxCoordinator
from .parse import box_objects, has_box
from .services import async_setup_services

type QidiBoxConfigEntry = ConfigEntry[QidiBoxCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Box entries waiting for their Moonraker entry to load: entry ID -> remover
# of the state listener on the Moonraker entry.
_WAITING = "waiting_for_moonraker"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Box actions."""
    async_setup_services(hass)
    return True


def client_for(hass: HomeAssistant, moonraker_entry: ConfigEntry) -> MoonrakerClient:
    """Return a client for the printer of a Moonraker config entry."""
    data = moonraker_entry.data
    try:
        port = int(data.get(MOONRAKER_CONF_PORT) or MOONRAKER_DEFAULT_PORT)
    except (TypeError, ValueError):
        port = MOONRAKER_DEFAULT_PORT
    return MoonrakerClient(
        async_get_clientsession(hass),
        data[MOONRAKER_CONF_URL],
        port,
        tls=bool(data.get(MOONRAKER_CONF_TLS)),
        api_key=data.get(MOONRAKER_CONF_API_KEY) or None,
    )


async def async_setup_entry(hass: HomeAssistant, entry: QidiBoxConfigEntry) -> bool:
    """Set up the Box once its Moonraker printer is loaded."""
    moonraker_id = entry.data[CONF_MOONRAKER_ENTRY_ID]
    moonraker_entry = hass.config_entries.async_get_entry(moonraker_id)
    if moonraker_entry is None or moonraker_entry.domain != MOONRAKER_DOMAIN:
        _async_stop_waiting(hass, entry.entry_id)
        raise ConfigEntryError(
            "The Moonraker printer this Box belongs to was removed; "
            "delete this entry and add the Box again"
        )
    # The Box's entities join the printer device the Moonraker entry creates.
    if moonraker_entry.state is not ConfigEntryState.LOADED:
        _async_retry_when_loaded(hass, entry, moonraker_entry)
        raise ConfigEntryNotReady(
            f"Waiting for Moonraker printer {moonraker_entry.title}"
        )
    _async_stop_waiting(hass, entry.entry_id)
    printer_device = dr.async_get(hass).async_get_device_by_identifier(
        (MOONRAKER_DOMAIN, moonraker_id), moonraker_id
    )
    if printer_device is None:
        raise ConfigEntryNotReady(f"Waiting for the {moonraker_entry.title} device")

    client = client_for(hass, moonraker_entry)
    try:
        objects = await client.objects_list()
    except MoonrakerError as err:
        raise ConfigEntryNotReady(f"{client.base_url} unreachable: {err}") from err
    if not has_box(objects):
        raise ConfigEntryNotReady(f"No QIDI Box reported by {client.base_url}")

    coordinator = QidiBoxCoordinator(
        hass, entry, client, box_objects(objects), moonraker_id, printer_device
    )
    await coordinator.async_refresh()
    if not coordinator.online:
        raise ConfigEntryNotReady(f"{client.base_url} unreachable")
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


@callback
def _async_retry_when_loaded(
    hass: HomeAssistant, entry: QidiBoxConfigEntry, moonraker_entry: ConfigEntry
) -> None:
    """Retry the Box setup as soon as its Moonraker entry loads.

    Setup retries back off to several minutes, so while the printer is off
    the Box would otherwise stay unavailable long after the printer is back.
    The listeners live outside the Box entry, because a failed setup runs the
    entry's unload callbacks. They are removed when the Box retries because
    Moonraker loaded or was removed, or when the Box stops retrying.
    """
    waiting = hass.data.setdefault(DOMAIN, {}).setdefault(_WAITING, {})
    if entry.entry_id in waiting:
        return

    @callback
    def _retry_now() -> None:
        _async_stop_waiting(hass, entry.entry_id)
        hass.config_entries.async_schedule_reload(entry.entry_id)

    @callback
    def _moonraker_state_changed() -> None:
        # While the Box sets up, wait for the result: if it ends in setup
        # retry, _box_state_changed sees that Moonraker has loaded.
        if (
            moonraker_entry.state is ConfigEntryState.LOADED
            and entry.state is ConfigEntryState.SETUP_RETRY
        ):
            _retry_now()

    @callback
    def _box_state_changed() -> None:
        if entry.state is ConfigEntryState.SETUP_RETRY:
            if moonraker_entry.state is ConfigEntryState.LOADED:
                _retry_now()
        elif entry.state is not ConfigEntryState.SETUP_IN_PROGRESS:
            _async_stop_waiting(hass, entry.entry_id)

    @callback
    def _entry_changed(change: ConfigEntryChange, changed: ConfigEntry) -> None:
        # Removing an entry doesn't change its state after it is unloaded.
        if (
            change is ConfigEntryChange.REMOVED
            and changed.entry_id == moonraker_entry.entry_id
        ):
            _retry_now()

    waiting[entry.entry_id] = (
        moonraker_entry.async_on_state_change(_moonraker_state_changed),
        entry.async_on_state_change(_box_state_changed),
        async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, _entry_changed),
    )


@callback
def _async_stop_waiting(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the state listeners of a waiting Box entry, if any."""
    removers = hass.data.get(DOMAIN, {}).get(_WAITING, {}).pop(entry_id, ())
    for remove in removers:
        # The listener may be running: Home Assistant iterates the listener
        # list, so remove it after the current callbacks.
        hass.loop.call_soon(remove)


async def _async_options_updated(
    hass: HomeAssistant, entry: QidiBoxConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: QidiBoxConfigEntry) -> bool:
    """Unload the Box."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: QidiBoxConfigEntry) -> None:
    """Stop waiting for the Moonraker entry of a removed Box."""
    _async_stop_waiting(hass, entry.entry_id)
