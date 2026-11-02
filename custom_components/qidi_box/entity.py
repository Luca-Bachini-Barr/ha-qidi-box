"""Base entity: attaches to the printer device of the Moonraker integration."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import QidiBoxCoordinator


class QidiBoxEntity(CoordinatorEntity[QidiBoxCoordinator]):
    """A Box entity on the Moonraker printer's device.

    Since Home Assistant 2026.8 a device belongs to one config entry, so a
    ``device_info`` with the printer's identifier would make a second device.
    Instead the entity links to the existing printer device (``device_entry``,
    as Home Assistant's own helpers do), so the Box sits with the printer's
    other entities: NextFloor and cards that read a device's entities see them
    together.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: QidiBoxCoordinator, key: str) -> None:
        """Set up the entity with a unique id built from the printer's entry id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.moonraker_entry_id}_{key}"
        self.device_entry = coordinator.printer_device

    @property
    def available(self) -> bool:
        """Return True while the printer answers."""
        return super().available and self.coordinator.online
