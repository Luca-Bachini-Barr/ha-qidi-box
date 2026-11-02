"""Polls the Box's Klipper objects from Moonraker."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import MoonrakerClient, MoonrakerError
from .const import (
    CONF_POLLING_RATE,
    DEFAULT_POLLING_RATE,
    DOMAIN,
    FAST_POLLING_RATE,
    IDLE_CHANGE_STATES,
)
from .parse import filament_change_state

_LOGGER = logging.getLogger(__name__)


class QidiBoxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds ``{"online": bool, "status": {object: fields}}`` for one printer's Box.

    A printer that is switched off is normal, not an error: the data says
    ``online: False`` (entities go unavailable) and nothing is logged above debug.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MoonrakerClient,
        objects: list[str],
        moonraker_entry_id: str,
        printer_device: DeviceEntry,
    ) -> None:
        """Set up the coordinator for ``objects`` of the printer behind ``client``."""
        self.idle_interval = timedelta(
            seconds=entry.options.get(CONF_POLLING_RATE, DEFAULT_POLLING_RATE)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=self.idle_interval,
        )
        self.client = client
        self.objects = objects
        self.moonraker_entry_id = moonraker_entry_id
        self.printer_device = printer_device
        self._fast_until = 0.0

    @property
    def status(self) -> dict[str, Any]:
        """Return the last status (empty while offline)."""
        return (self.data or {}).get("status") or {}

    @property
    def online(self) -> bool:
        """Return True when the last poll reached the printer."""
        return bool((self.data or {}).get("online"))

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.client.query(self.objects)
        except MoonrakerError as err:
            if self.online or self.data is None:
                _LOGGER.debug("%s unreachable: %s", self.client.base_url, err)
            data: dict[str, Any] = {"online": False, "status": {}}
        else:
            data = {"online": True, "status": status}
        self._set_interval(data)
        return data

    def _set_interval(self, data: dict[str, Any]) -> None:
        changing = data["online"] and (
            filament_change_state(data["status"]) not in IDLE_CHANGE_STATES
        )
        fast = changing or time.monotonic() < self._fast_until
        self.update_interval = (
            timedelta(seconds=FAST_POLLING_RATE) if fast else self.idle_interval
        )

    async def async_poll_fast_for(self, seconds: float) -> None:
        """Poll every few seconds for ``seconds`` (after a command), starting now."""
        self._fast_until = time.monotonic() + seconds
        await self.async_request_refresh()
