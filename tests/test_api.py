"""The Moonraker HTTP client."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.qidi_box.api import CannotConnect, GcodeError, MoonrakerClient

BASE = "http://192.168.1.24:7125"


async def test_requests(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """List, query and G-code, with the API key header."""
    aioclient_mock.get(
        f"{BASE}/printer/objects/list", json={"result": {"objects": ["box_extras", 3]}}
    )
    aioclient_mock.post(
        f"{BASE}/printer/objects/query",
        json={"result": {"status": {"box_extras": {"loaded_slot": "slot16"}}}},
    )
    aioclient_mock.post(f"{BASE}/printer/gcode/script", json={"result": "ok"})
    client = MoonrakerClient(
        async_get_clientsession(hass), "http://192.168.1.24/", 7125, api_key="k"
    )
    assert client.base_url == BASE
    assert await client.objects_list() == ["box_extras"]
    assert await client.query(["box_extras"]) == {
        "box_extras": {"loaded_slot": "slot16"}
    }
    await client.gcode("G28")
    assert aioclient_mock.mock_calls[1][2] == {"objects": {"box_extras": None}}
    assert aioclient_mock.mock_calls[2][2] == {"script": "G28"}
    assert aioclient_mock.mock_calls[2][3] == {"X-Api-Key": "k"}


async def test_tls_and_empty_answers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """https with tls; odd answers give empty results."""
    aioclient_mock.get("https://p:7130/printer/objects/list", text="not json")
    aioclient_mock.post("https://p:7130/printer/objects/query", json={"result": []})
    client = MoonrakerClient(async_get_clientsession(hass), "p", 7130, tls=True)
    assert await client.objects_list() == []
    assert await client.query(["x"]) == {}


async def test_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Klipper's error message; connection failures."""
    aioclient_mock.post(
        f"{BASE}/printer/gcode/script",
        status=400,
        json={"error": {"code": 400, "message": 'Unknown command:"FOO"'}},
    )
    aioclient_mock.get(
        f"{BASE}/printer/objects/list", exc=aiohttp.ClientConnectionError()
    )
    aioclient_mock.post(f"{BASE}/printer/objects/query", exc=TimeoutError())
    client = MoonrakerClient(async_get_clientsession(hass), "192.168.1.24", 7125)
    with pytest.raises(GcodeError, match="Unknown command"):
        await client.gcode("FOO")
    with pytest.raises(CannotConnect):
        await client.objects_list()
    with pytest.raises(CannotConnect):
        await client.query(["x"])

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/printer/gcode/script", status=500, text="boom")
    with pytest.raises(GcodeError, match="HTTP 500"):
        await client.gcode("G28")
