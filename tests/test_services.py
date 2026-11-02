"""Box actions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qidi_box.api import GcodeError
from custom_components.qidi_box.const import DOMAIN

from .conftest import MOONRAKER_ENTRY_ID, setup_box


@pytest.fixture
async def device_id(
    hass: HomeAssistant, box_entry: MockConfigEntry, client: AsyncMock
) -> str:
    """Set up the Box and return the printer's device id."""
    await setup_box(hass, box_entry)
    return (
        dr.async_get(hass)
        .async_get_device_by_identifier(
            ("moonraker", MOONRAKER_ENTRY_ID), MOONRAKER_ENTRY_ID
        )
        .id
    )


@pytest.mark.parametrize(
    ("service", "gcode"),
    [
        ("load_filament", "LOAD_FILAMENT_CONTROL SLOT=2"),
        ("unload_filament", "UNLOAD_FILAMENT_CONTROL SLOT=2"),
        ("eject_filament", "EJECT_FILAMENT_CONTROL SLOT=2"),
    ],
)
async def test_slot_actions(
    hass: HomeAssistant, device_id: str, client: AsyncMock, service: str, gcode: str
) -> None:
    """Slot 3 in Home Assistant is SLOT=2 (0-based) in G-code."""
    await hass.services.async_call(
        DOMAIN, service, {"device_id": device_id, "slot": 3}, blocking=True
    )
    client.gcode.assert_awaited_with(gcode)


async def test_set_slot_filament(
    hass: HomeAssistant, device_id: str, client: AsyncMock
) -> None:
    """The touchscreen's UPDATE_FILAMENT_INFORMATION, with the filament NAME."""
    await hass.services.async_call(
        DOMAIN,
        "set_slot_filament",
        {
            "device_id": device_id,
            "slot": 1,
            "color": "#22833a",
            "vendor": "Generic",
            "filament": "PLA+",
        },
        blocking=True,
    )
    client.gcode.assert_awaited_with(
        "UPDATE_FILAMENT_INFORMATION SLOT=0 COLOR='22833A' VENDOR='Generic' FILAMENT='PLA+'"
    )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "set_slot_filament",
            {
                "device_id": device_id,
                "slot": 1,
                "color": "x",
                "vendor": "a",
                "filament": "b",
            },
            blocking=True,
        )


async def test_send_gcode(
    hass: HomeAssistant, device_id: str, client: AsyncMock
) -> None:
    """Raw G-code, as text or a list; Klipper's error is reported."""
    await hass.services.async_call(
        DOMAIN,
        "send_gcode",
        {"device_id": device_id, "gcode": ["G28", "", "M400"]},
        blocking=True,
    )
    client.gcode.assert_awaited_with("G28\nM400")

    client.gcode.side_effect = GcodeError("Unknown command: FOO")
    with pytest.raises(HomeAssistantError, match="Unknown command: FOO"):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {"device_id": device_id, "gcode": "FOO"},
            blocking=True,
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "send_gcode", {"device_id": device_id, "gcode": "  "}, blocking=True
        )


async def test_long_command_returns_early(
    hass: HomeAssistant,
    device_id: str,
    client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With wait=false a long command returns after the accept timeout; a fast error still raises."""
    finish = asyncio.Event()

    async def slow(_script: str) -> None:
        await finish.wait()
        raise GcodeError("late failure")

    client.gcode.side_effect = slow
    with patch("custom_components.qidi_box.services.GCODE_ACCEPT_TIMEOUT", 0.01):
        await hass.services.async_call(
            DOMAIN, "load_filament", {"device_id": device_id, "slot": 3}, blocking=True
        )
    finish.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "late failure" in caplog.text

    client.gcode.side_effect = GcodeError("unable to parse slot9")
    with pytest.raises(HomeAssistantError, match="unable to parse"):
        await hass.services.async_call(
            DOMAIN, "load_filament", {"device_id": device_id, "slot": 3}, blocking=True
        )


async def test_device_without_box(
    hass: HomeAssistant, device_id: str, client: AsyncMock
) -> None:
    """Actions on unknown devices or devices without a Box are refused."""
    other = MockConfigEntry(domain="moonraker", entry_id="other")
    other.add_to_hass(hass)
    plain = dr.async_get(hass).async_get_or_create(
        config_entry_id="other", identifiers={("moonraker", "other")}, name="Plain"
    )
    for target in ("nope", plain.id):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "load_filament", {"device_id": target, "slot": 1}, blocking=True
            )


async def test_box_not_loaded(
    hass: HomeAssistant, device_id: str, box_entry: MockConfigEntry, client: AsyncMock
) -> None:
    """A Box entry that is not loaded cannot run actions."""
    await hass.config_entries.async_unload(box_entry.entry_id)
    with pytest.raises(HomeAssistantError, match="not loaded"):
        await hass.services.async_call(
            DOMAIN, "load_filament", {"device_id": device_id, "slot": 1}, blocking=True
        )


async def test_heater_target(
    hass: HomeAssistant, device_id: str, client: AsyncMock
) -> None:
    """The Box heater target sends SET_HEATER_TEMPERATURE."""
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.q2_heater_box1_target", "value": 50},
        blocking=True,
    )
    client.gcode.assert_awaited_with(
        "SET_HEATER_TEMPERATURE HEATER=heater_box1 TARGET=50"
    )

    client.gcode.side_effect = GcodeError("nope")
    with pytest.raises(HomeAssistantError, match="heater_box1"):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.q2_heater_box1_target", "value": 40},
            blocking=True,
        )


async def test_late_results_logged(
    hass: HomeAssistant,
    device_id: str,
    client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A long command that later succeeds is logged at debug, a late failure as a warning."""
    finish = asyncio.Event()

    async def slow(_script: str) -> None:
        await finish.wait()

    client.gcode.side_effect = slow
    with patch("custom_components.qidi_box.services.GCODE_ACCEPT_TIMEOUT", 0.01):
        await hass.services.async_call(
            DOMAIN,
            "unload_filament",
            {"device_id": device_id, "slot": 1},
            blocking=True,
        )
    finish.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "late failure" not in caplog.text


def test_late_result_cancelled() -> None:
    """A cancelled background command (shutdown) logs nothing."""
    from custom_components.qidi_box.services import _log_late_result

    task = AsyncMock()
    task.cancelled = lambda: True
    _log_late_result(task, "G28")
