"""A minimal Moonraker HTTP client: list and query Klipper objects, run G-code."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import GCODE_TIMEOUT, REQUEST_TIMEOUT


class MoonrakerError(Exception):
    """Base error talking to Moonraker."""


class CannotConnect(MoonrakerError):
    """Moonraker is unreachable (printer off, network down)."""


class GcodeError(MoonrakerError):
    """Klipper rejected a G-code script; the message is Klipper's."""


class MoonrakerClient:
    """Talks to one printer's Moonraker over HTTP."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        *,
        tls: bool = False,
        api_key: str | None = None,
    ) -> None:
        """Set up the client; ``host`` may carry a scheme, which is dropped."""
        host = host.strip().rstrip("/")
        for scheme in ("http://", "https://"):
            if host.startswith(scheme):
                host = host[len(scheme) :]
        self._session = session
        self._base = f"{'https' if tls else 'http'}://{host}:{port}"
        self._headers = {"X-Api-Key": api_key} if api_key else {}

    @property
    def base_url(self) -> str:
        """Return the Moonraker base URL."""
        return self._base

    async def _request(
        self, method: str, path: str, *, json: Any = None, timeout: float
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                json=json,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = None
                if resp.status >= 400:
                    raise GcodeError(_error_message(body) or f"HTTP {resp.status}")
                return body.get("result") if isinstance(body, dict) else None
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(str(err) or type(err).__name__) from err

    async def objects_list(self) -> list[str]:
        """Return the names of the printer's Klipper objects."""
        result = await self._request(
            "GET", "/printer/objects/list", timeout=REQUEST_TIMEOUT
        )
        objects = result.get("objects") if isinstance(result, dict) else None
        return [obj for obj in objects if isinstance(obj, str)] if objects else []

    async def query(self, objects: list[str]) -> dict[str, Any]:
        """Return the full status of ``objects``."""
        result = await self._request(
            "POST",
            "/printer/objects/query",
            json={"objects": dict.fromkeys(objects)},
            timeout=REQUEST_TIMEOUT,
        )
        status = result.get("status") if isinstance(result, dict) else None
        return status if isinstance(status, dict) else {}

    async def gcode(self, script: str, *, timeout: float = GCODE_TIMEOUT) -> None:
        """Run a G-code script; returns when Klipper has finished it."""
        await self._request(
            "POST", "/printer/gcode/script", json={"script": script}, timeout=timeout
        )


def _error_message(body: Any) -> str | None:
    """Return Moonraker's error message (``{"error": {"message": ...}}``)."""
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    return str(message) if message else None
