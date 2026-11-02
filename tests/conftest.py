"""Fixtures: a loaded Moonraker printer entry with its device, and a mocked Moonraker."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qidi_box.const import CONF_MOONRAKER_ENTRY_ID, DOMAIN

PYTEST_PLUGINS = "pytest_homeassistant_custom_component"

# A real Q2 + Box 1 (printer/objects/query, 2026-11-02): slots 1-2 empty, 3-4 PLA Basic black
Q2 = json.loads((Path(__file__).parent / "q2_status.json").read_text())["result"][
    "status"
]
OBJECTS = [
    "webhooks",
    "extruder",
    "heater_bed",
    "mcu mcu_box1",
    "heater_generic chamber",
    "aht20_f heater_box1",
    *Q2,
]
MOONRAKER_ENTRY_ID = "01MOONRAKERENTRY"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom integrations in every test."""
    yield


def q2_status(**changes: Any) -> dict[str, Any]:
    """Return a copy of the Q2 status with top-level objects replaced or merged."""
    status = copy.deepcopy(Q2)
    for obj, value in changes.items():
        status[obj.replace("__", " ")] = value
    return status


@pytest.fixture
def moonraker_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A loaded Moonraker printer entry and its device, as the Moonraker integration makes them."""
    entry = MockConfigEntry(
        domain="moonraker",
        entry_id=MOONRAKER_ENTRY_ID,
        title="Q2",
        data={"url": "192.168.1.24", "port": 7125, "api_key": "", "printer_name": ""},
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("moonraker", MOONRAKER_ENTRY_ID)},
        name="Q2",
        manufacturer="moonraker",
        model="moonraker",
    )
    return entry


@pytest.fixture
def box_entry(hass: HomeAssistant, moonraker_entry: MockConfigEntry) -> MockConfigEntry:
    """The QIDI Box entry for the printer (not set up)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="QIDI Box (Q2)",
        unique_id=MOONRAKER_ENTRY_ID,
        data={CONF_MOONRAKER_ENTRY_ID: MOONRAKER_ENTRY_ID},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def client() -> AsyncMock:
    """A mocked Moonraker client answering like the Q2."""
    mock = AsyncMock()
    mock.base_url = "http://192.168.1.24:7125"
    mock.objects_list.return_value = list(OBJECTS)
    mock.query.return_value = q2_status()
    mock.gcode.return_value = None
    with (
        patch("custom_components.qidi_box.MoonrakerClient", return_value=mock),
    ):
        yield mock


async def setup_box(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the Box entry."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
