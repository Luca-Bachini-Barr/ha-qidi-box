"""Setting up the Box on the Moonraker printer device."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.qidi_box.api import CannotConnect
from custom_components.qidi_box.const import CONF_POLLING_RATE

from .conftest import MOONRAKER_ENTRY_ID, q2_status, setup_box

SLOT_3 = "sensor.q2_box_slot_3_filament"


async def test_entities_join_printer_device(
    hass: HomeAssistant, box_entry: MockConfigEntry, client: AsyncMock
) -> None:
    """Every Box entity sits on the Moonraker printer's device; no new device is made."""
    await setup_box(hass, box_entry)
    assert box_entry.state is ConfigEntryState.LOADED

    devices = dr.async_get(hass)
    printer = devices.async_get_device_by_identifier(
        ("moonraker", MOONRAKER_ENTRY_ID), MOONRAKER_ENTRY_ID
    )
    assert printer is not None
    assert printer.name == "Q2"
    assert len(devices.devices) == 1
    assert printer.config_entry_id == MOONRAKER_ENTRY_ID

    entities = er.async_entries_for_config_entry(er.async_get(hass), box_entry.entry_id)
    assert sorted(e.entity_id for e in entities) == [
        "binary_sensor.q2_box_1_drying",
        "number.q2_heater_box1_target",
        "sensor.q2_box_filament_change",
        "sensor.q2_box_slot_1_filament",
        "sensor.q2_box_slot_2_filament",
        "sensor.q2_box_slot_3_filament",
        "sensor.q2_box_slot_4_filament",
        "sensor.q2_box_warnings",
    ]
    assert {e.device_id for e in entities} == {printer.id}
    assert entities[0].unique_id.startswith(MOONRAKER_ENTRY_ID)

    state = hass.states.get(SLOT_3)
    assert state.state == "PLA Basic"
    assert state.attributes["color"] == "#060606"
    assert state.attributes["active"] is False
    assert hass.states.get("sensor.q2_box_slot_1_filament").attributes["color"] is None
    assert hass.states.get("binary_sensor.q2_box_1_drying").state == "off"
    assert hass.states.get("sensor.q2_box_filament_change").state == "idle"
    assert hass.states.get("sensor.q2_box_warnings").state == "0"
    assert hass.states.get("number.q2_heater_box1_target").state == "0.0"

    client.query.assert_awaited_with(
        [
            "box_extras",
            "save_variables",
            "multi_color_controller",
            "box_stepper slot0",
            "box_stepper slot1",
            "box_stepper slot2",
            "box_stepper slot3",
            "heater_generic heater_box1",
        ]
    )

    assert await hass.config_entries.async_unload(box_entry.entry_id)
    assert box_entry.state is ConfigEntryState.NOT_LOADED


async def test_printer_off_and_back(
    hass: HomeAssistant,
    box_entry: MockConfigEntry,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A printer switched off makes the entities unavailable, and they come back."""
    await setup_box(hass, box_entry)
    client.query.side_effect = CannotConnect("off")
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SLOT_3).state == STATE_UNAVAILABLE

    client.query.side_effect = None
    client.query.return_value = q2_status()
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SLOT_3).state == "PLA Basic"


@pytest.mark.parametrize("missing", [{}, {"box_extras": None}])
async def test_box_offline_and_back(
    hass: HomeAssistant,
    box_entry: MockConfigEntry,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    missing: dict[str, None],
) -> None:
    """A printer up without its Box must not show saved filaments as loaded."""
    await setup_box(hass, box_entry)
    client.query.return_value = {
        "save_variables": q2_status()["save_variables"],
        **missing,
    }
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    for entity_id in (
        SLOT_3,
        "binary_sensor.q2_box_1_drying",
        "number.q2_heater_box1_target",
        "sensor.q2_box_filament_change",
        "sensor.q2_box_warnings",
    ):
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE, entity_id

    client.query.return_value = q2_status()
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SLOT_3).state == "PLA Basic"


async def test_fast_polling_during_change(
    hass: HomeAssistant, box_entry: MockConfigEntry, client: AsyncMock
) -> None:
    """The Box is polled every 2 s while a filament change runs."""
    await setup_box(hass, box_entry)
    coordinator = box_entry.runtime_data
    assert coordinator.update_interval == timedelta(seconds=10)

    status = q2_status()
    status["multi_color_controller"]["task"]["flow_id"] = 3
    client.query.return_value = status
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(seconds=2)

    client.query.return_value = q2_status()
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(seconds=10)


async def test_polling_option(
    hass: HomeAssistant, box_entry: MockConfigEntry, client: AsyncMock
) -> None:
    """The idle polling rate is an option; changing it reloads the entry."""
    hass.config_entries.async_update_entry(box_entry, options={CONF_POLLING_RATE: 30})
    await setup_box(hass, box_entry)
    assert box_entry.runtime_data.update_interval == timedelta(seconds=30)

    result = await hass.config_entries.options.async_init(box_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLLING_RATE: 15}
    )
    await hass.async_block_till_done()
    assert box_entry.options == {CONF_POLLING_RATE: 15}
    assert box_entry.runtime_data.update_interval == timedelta(seconds=15)


async def test_waits_for_moonraker(
    hass: HomeAssistant,
    box_entry: MockConfigEntry,
    moonraker_entry: MockConfigEntry,
    client: AsyncMock,
) -> None:
    """The Box waits while the Moonraker printer is not loaded or unreachable."""
    moonraker_entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    await hass.config_entries.async_setup(box_entry.entry_id)
    assert box_entry.state is ConfigEntryState.SETUP_RETRY
    client.objects_list.assert_not_awaited()


async def test_waits_for_device(
    hass: HomeAssistant, box_entry: MockConfigEntry, client: AsyncMock
) -> None:
    """Without the printer device yet, the Box waits."""
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        ("moonraker", MOONRAKER_ENTRY_ID), MOONRAKER_ENTRY_ID
    )
    devices.async_remove_device(device.id)
    await hass.config_entries.async_setup(box_entry.entry_id)
    assert box_entry.state is ConfigEntryState.SETUP_RETRY


async def test_not_ready_when_unreachable_or_no_box(
    hass: HomeAssistant, box_entry: MockConfigEntry, client: AsyncMock
) -> None:
    """Unreachable printer, no Box, or a failed first poll: retry later."""
    client.objects_list.side_effect = CannotConnect("off")
    await hass.config_entries.async_setup(box_entry.entry_id)
    assert box_entry.state is ConfigEntryState.SETUP_RETRY

    client.objects_list.side_effect = None
    client.objects_list.return_value = ["extruder"]
    await hass.config_entries.async_reload(box_entry.entry_id)
    assert box_entry.state is ConfigEntryState.SETUP_RETRY

    client.objects_list.return_value = list(q2_status())
    client.query.side_effect = CannotConnect("off")
    await hass.config_entries.async_reload(box_entry.entry_id)
    assert box_entry.state is ConfigEntryState.SETUP_RETRY


async def test_moonraker_entry_removed(
    hass: HomeAssistant,
    box_entry: MockConfigEntry,
    moonraker_entry: MockConfigEntry,
    client: AsyncMock,
) -> None:
    """If the printer's Moonraker entry is gone, the Box entry fails for good."""
    moonraker_entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    await hass.config_entries.async_remove(moonraker_entry.entry_id)
    await hass.config_entries.async_setup(box_entry.entry_id)
    assert box_entry.state is ConfigEntryState.SETUP_ERROR


async def test_bad_port_falls_back(
    hass: HomeAssistant, box_entry: MockConfigEntry, moonraker_entry: MockConfigEntry
) -> None:
    """An unusable port in the Moonraker entry falls back to 7125."""
    from custom_components.qidi_box import client_for

    hass.config_entries.async_update_entry(
        moonraker_entry, data={**moonraker_entry.data, "port": "abc"}
    )
    assert client_for(hass, moonraker_entry).base_url == "http://192.168.1.24:7125"
