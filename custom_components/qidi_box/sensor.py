"""Box slot filament, filament change and warning sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import QidiBoxConfigEntry
from .coordinator import QidiBoxCoordinator
from .entity import QidiBoxEntity
from .parse import (
    box_warnings,
    filament_change_attributes,
    filament_change_state,
    slot_attributes,
    slot_filament,
    slot_index,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QidiBoxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a filament sensor per slot, and change/warning sensors on Box V2 firmware."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        SlotFilamentSensor(coordinator, index)
        for index in sorted(
            i for i in map(slot_index, coordinator.objects) if i is not None
        )
    ]
    if "multi_color_controller" in coordinator.objects:
        entities += [FilamentChangeSensor(coordinator), BoxWarningsSensor(coordinator)]
    async_add_entities(entities)


class SlotFilamentSensor(QidiBoxEntity, SensorEntity):
    """The filament in one slot (``Empty`` when the runout switch says so)."""

    _attr_icon = "mdi:spool"

    def __init__(self, coordinator: QidiBoxCoordinator, index: int) -> None:
        """Set up the sensor for 0-based slot ``index`` (named 1-based)."""
        super().__init__(coordinator, f"box_slot{index}_filament")
        self._index = index
        self._attr_name = f"Box Slot {index + 1} Filament"

    @property
    def native_value(self) -> str | None:
        """Return the filament name or ``Empty``."""
        return slot_filament(self.coordinator.status, self._index)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return colour, vendor, type, temperatures and whether it feeds the toolhead."""
        return slot_attributes(self.coordinator.status, self._index)


class FilamentChangeSensor(QidiBoxEntity, SensorEntity):
    """The step of a running filament change (``idle`` otherwise)."""

    _attr_icon = "mdi:swap-horizontal-circle-outline"
    _attr_name = "Box Filament Change"

    def __init__(self, coordinator: QidiBoxCoordinator) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, "box_filament_change")

    @property
    def native_value(self) -> str | None:
        """Return the change step."""
        return filament_change_state(self.coordinator.status)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return target and loaded slot, steps and warnings."""
        return filament_change_attributes(self.coordinator.status)


class BoxWarningsSensor(QidiBoxEntity, SensorEntity):
    """The number of Box warnings, with the warnings as an attribute."""

    _attr_icon = "mdi:alert-outline"
    _attr_name = "Box Warnings"

    def __init__(self, coordinator: QidiBoxCoordinator) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, "box_warnings")

    @property
    def native_value(self) -> int:
        """Return how many warnings the Box reports."""
        return len(box_warnings(self.coordinator.status))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the warnings."""
        return {"warnings": box_warnings(self.coordinator.status)}
