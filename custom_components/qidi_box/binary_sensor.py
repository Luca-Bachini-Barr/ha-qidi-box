"""Box drying binary sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import QidiBoxConfigEntry
from .coordinator import QidiBoxCoordinator
from .entity import QidiBoxEntity
from .parse import box_label, drying_active, drying_box_keys


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QidiBoxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a drying sensor for every box that reports a drying state."""
    coordinator = entry.runtime_data
    async_add_entities(
        BoxDryingSensor(coordinator, key) for key in drying_box_keys(coordinator.status)
    )


class BoxDryingSensor(QidiBoxEntity, BinarySensorEntity):
    """On while the box dries its filament."""

    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: QidiBoxCoordinator, box_key: str) -> None:
        """Set up the sensor for ``box1``, ``box2`` …."""
        super().__init__(coordinator, f"{box_key}_drying")
        self._box_key = box_key
        self._attr_name = f"{box_label(box_key)} Drying"

    @property
    def is_on(self) -> bool:
        """Return True while drying."""
        return drying_active(self.coordinator.status, self._box_key)
