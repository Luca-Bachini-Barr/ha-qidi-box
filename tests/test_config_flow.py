"""Adding a Box."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qidi_box.api import CannotConnect
from custom_components.qidi_box.const import CONF_MOONRAKER_ENTRY_ID, DOMAIN

from .conftest import MOONRAKER_ENTRY_ID


@pytest.fixture(autouse=True)
def no_setup():
    """Do not set the entry up after the flow."""
    with patch("custom_components.qidi_box.async_setup_entry", return_value=True):
        yield


async def test_add_box(
    hass: HomeAssistant, moonraker_entry: MockConfigEntry, client: AsyncMock
) -> None:
    """Pick the printer; the entry stores only its Moonraker entry id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MOONRAKER_ENTRY_ID: MOONRAKER_ENTRY_ID}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "QIDI Box (Q2)"
    assert result["data"] == {CONF_MOONRAKER_ENTRY_ID: MOONRAKER_ENTRY_ID}
    assert result["result"].unique_id == MOONRAKER_ENTRY_ID

    # the only printer now has a Box: nothing left to add
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_printers"


async def test_no_printers(hass: HomeAssistant) -> None:
    """Without the Moonraker integration there is nothing to add to."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_printers"


async def test_errors(
    hass: HomeAssistant, moonraker_entry: MockConfigEntry, client: AsyncMock
) -> None:
    """Unreachable printer, no Box, printer not loaded, printer gone."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    flow = result["flow_id"]

    client.objects_list.side_effect = CannotConnect("off")
    result = await hass.config_entries.flow.async_configure(
        flow, {CONF_MOONRAKER_ENTRY_ID: MOONRAKER_ENTRY_ID}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    client.objects_list.side_effect = None
    client.objects_list.return_value = ["extruder"]
    result = await hass.config_entries.flow.async_configure(
        flow, {CONF_MOONRAKER_ENTRY_ID: MOONRAKER_ENTRY_ID}
    )
    assert result["errors"] == {"base": "no_box"}

    moonraker_entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    result = await hass.config_entries.flow.async_configure(
        flow, {CONF_MOONRAKER_ENTRY_ID: MOONRAKER_ENTRY_ID}
    )
    assert result["errors"] == {"base": "printer_not_loaded"}

    with patch.object(hass.config_entries, "async_get_entry", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            flow, {CONF_MOONRAKER_ENTRY_ID: MOONRAKER_ENTRY_ID}
        )
    assert result["errors"] == {"base": "unknown_printer"}
