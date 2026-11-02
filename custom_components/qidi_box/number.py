"""Box heater (drying) target temperature."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import QidiBoxConfigEntry
from .api import MoonrakerError
from .const import COMMAND_FAST_POLL_SECONDS
from .coordinator import QidiBoxCoordinator
from .entity import QidiBoxEntity
from .parse import box_heater

# The Box heater has no [heater_generic] config section to read a max_temp from
BOX_HEATER_MAX = 100


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QidiBoxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a target temperature for every Box heater."""
    coordinator = entry.runtime_data
    async_add_entities(
        BoxHeaterTarget(coordinator, obj, heater)
        for obj in coordinator.objects
        if (heater := box_heater(obj))
    )


class BoxHeaterTarget(QidiBoxEntity, NumberEntity):
    """The target temperature of a Box heater; 0 turns it off."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_icon = "mdi:radiator"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = BOX_HEATER_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: QidiBoxCoordinator, obj: str, heater: str) -> None:
        """Set up the target for Klipper object ``obj`` (heater ``heater``)."""
        super().__init__(coordinator, f"{heater}_target")
        self._obj = obj
        self._heater = heater
        self._attr_name = f"{heater.replace('_', ' ').title()} Target"

    @property
    def native_value(self) -> float | None:
        """Return the current target."""
        target = (self.coordinator.status.get(self._obj) or {}).get("target")
        return float(target) if isinstance(target, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the target."""
        try:
            await self.coordinator.client.gcode(
                f"SET_HEATER_TEMPERATURE HEATER={self._heater} TARGET={value:g}"
            )
        except MoonrakerError as err:
            raise HomeAssistantError(f"Could not set {self._heater}: {err}") from err
        await self.coordinator.async_poll_fast_for(COMMAND_FAST_POLL_SECONDS)
