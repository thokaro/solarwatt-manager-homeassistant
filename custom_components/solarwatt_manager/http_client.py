from __future__ import annotations

import time
from typing import Any

from aiohttp import ClientSession

from .client import SolarwattAuthError, SolarwattProtocolError


class SolarwattHttpClient:
    """Shared HTTP helper for SOLARWATT local APIs."""

    def __init__(self, session: ClientSession, get_base, set_base, login_callback, log):
        self._session = session
        self._get_base = get_base
        self._set_base = set_base
        self._login_callback = login_callback
        self._log = log

    @staticmethod
    def request_kwargs(url: str) -> dict[str, Any]:
        return {"ssl": False} if url.startswith("https://") else {}

    @staticmethod
    def base_from_url(url) -> str | None:
        try:
            scheme = url.scheme
            host = url.host
            port = url.port
        except Exception:
            return None

        if not scheme or not host:
            return None

        default_port = 80 if scheme == "http" else 443 if scheme == "https" else None
        if port and port != default_port:
            return f"{scheme}://{host}:{port}"

        return f"{scheme}://{host}"

    @staticmethod
    def looks_like_login_page(snippet: str) -> bool:
        lower = snippet.lower()
        return any(
            marker in lower
            for marker in (
                'action="/auth/login"',
                "please enter the gateway password",
                '<h3 class="primary-color">sign in</h3>',
                "kiwios-app-frame",
            )
        )

    def request(self, method: str, url: str, **kwargs):
        request_kwargs = dict(kwargs)
        request_kwargs.update(self.request_kwargs(url))
        return self._session.request(method, url, **request_kwargs)

    async def read_snippet(self, resp, limit: int = 300) -> str:
        try:
            text = await resp.text()
            text = text.replace("\n", " ").replace("\r", " ")
            return text[:limit]
        except Exception:
            return "<unreadable>"

    async def ensure_json(self, resp, where: str, cookie_debug: str) -> Any:
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "json" not in ct:
            snippet = await self.read_snippet(resp)
            raise SolarwattProtocolError(
                f"Antwort ist kein JSON bei {where}. Status={resp.status}, "
                f"Content-Type={ct or '<none>'}, Cookies={cookie_debug}, Snippet={snippet}"
            )
        return await resp.json()

    async def get_json_endpoint(
        self,
        path: str,
        *,
        where: str,
        cookie_debug: str,
    ) -> Any:
        """Fetch a JSON endpoint with one re-authentication retry."""
        for attempt in range(2):
            base = self._get_base()
            url = f"{base}{path}"

            async with self.request("GET", url, timeout=5) as resp:
                redirected_base = self.base_from_url(resp.url)
                if redirected_base:
                    self._set_base(redirected_base)

                if resp.status in (401, 403):
                    if attempt == 0:
                        await self._login_callback()
                        continue
                    resp.raise_for_status()

                ct = (resp.headers.get("Content-Type") or "").lower()

                if "text/html" in ct and attempt == 0:
                    await self._login_callback()
                    continue

                if "text/html" in ct:
                    snippet = await self.read_snippet(resp)
                    if self.looks_like_login_page(snippet):
                        raise SolarwattAuthError(f"Session expired while requesting {where}")

                resp.raise_for_status()
                return await self.ensure_json(resp, where, cookie_debug)