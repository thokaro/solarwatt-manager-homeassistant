from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, CookieJar
from homeassistant.helpers.update_coordinator import UpdateFailed


class SolarwattError(UpdateFailed):
    """Base error for SOLARWATT client failures."""


class SolarwattAuthError(SolarwattError):
    """Authentication failed."""


class SolarwattConnectionError(SolarwattError):
    """Connection or transport error."""


class SolarwattNotManagerError(SolarwattError):
    """Host does not look like a SOLARWATT Manager."""


class SolarwattProtocolError(SolarwattError):
    """Unexpected response format or protocol mismatch."""


class SOLARWATTClient:
    def __init__(self, hass, host: str, username: str, password: str):
        if not host or not isinstance(host, str):
            raise ValueError("host must be a non-empty string")
        if not username or not isinstance(username, str):
            raise ValueError("username must be a non-empty string")
        if not password or not isinstance(password, str):
            raise ValueError("password must be a non-empty string")

        self.hass = hass
        self.host = host
        self.username = username
        self.password = password

        self._candidate_bases = [f"http://{host}", f"https://{host}"]
        self.base = self._candidate_bases[0]

        self._session = ClientSession(cookie_jar=CookieJar(unsafe=True))
        self.session_ttl = 900
        self._last_login = 0.0
        self._log = logging.getLogger(__name__)

    def _set_base(self, base: str) -> None:
        self.base = base.rstrip("/")

    @staticmethod
    def _base_from_url(url) -> str | None:
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
    def _looks_like_login_page(snippet: str) -> bool:
        lower = snippet.lower()
        return any(
            marker in lower
            for marker in (
                'action="/auth/login"',
                "please enter the gateway password",
                "<h3 class=\"primary-color\">sign in</h3>",
                "kiwios-app-frame",
            )
        )

    @staticmethod
    def _request_kwargs(url: str) -> dict[str, Any]:
        # Newer managers can redirect to or expose HTTPS with a self-signed cert.
        return {"ssl": False} if url.startswith("https://") else {}

    def _has_session_cookies(self) -> bool:
        try:
            jar_cookies = self._session.cookie_jar.filter_cookies(self.base)
            return any(morsel.value for morsel in jar_cookies.values())
        except Exception:
            return False

    def _cookie_debug(self) -> str:
        try:
            jar_cookies = self._session.cookie_jar.filter_cookies(self.base)
            names = [morsel.key for morsel in jar_cookies.values() if morsel.value]
            return ",".join(names) if names else "<none>"
        except Exception:
            return "<unknown>"

    async def _read_snippet(self, resp, limit: int = 300) -> str:
        try:
            text = await resp.text()
            text = text.replace("\n", " ").replace("\r", " ")
            return text[:limit]
        except Exception:
            return "<unreadable>"

    def _request(self, method: str, url: str, **kwargs):
        request_kwargs = dict(kwargs)
        request_kwargs.update(self._request_kwargs(url))
        return self._session.request(method, url, **request_kwargs)

    async def async_close(self) -> None:
        if not self._session.closed:
            await self._session.close()

    async def async_login(self) -> None:
        usernames = [self.username]
        if self.username != "installer":
            usernames.append("installer")

        last_auth_error: SolarwattAuthError | None = None
        last_connection_error: SolarwattConnectionError | None = None
        last_not_manager_error: SolarwattNotManagerError | None = None

        for base in self._candidate_bases:
            self._set_base(base)
            for username in usernames:
                resp_status: int | None = None
                resp_headers: dict[str, str] = {}
                resp_ct: str = ""

                payload = {
                    "username": username,
                    "password": self.password,
                    "url": "/",
                    "submit": "Login",
                }

                try:
                    async with self._request(
                        "POST",
                        f"{self.base}/auth/login",
                        data=payload,
                        timeout=5,
                        allow_redirects=False,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ) as resp:
                        resp_status = resp.status
                        resp_headers = dict(resp.headers)
                        resp_ct = (resp.headers.get("Content-Type") or "").lower()

                        redirected_base = self._base_from_url(resp.url)
                        if redirected_base:
                            self._set_base(redirected_base)

                        if resp.status in (401, 403):
                            text = await resp.text()
                            raise SolarwattAuthError(
                                f"Login failed ({resp.status}): {text[:200]}"
                            )
                        if resp.status == 404:
                            raise SolarwattNotManagerError(
                                f"Login endpoint not found ({resp.status})"
                            )
                        if not 200 <= resp.status < 400:
                            text = await resp.text()
                            raise SolarwattConnectionError(
                                f"Login failed ({resp.status}): {text[:200]}"
                            )

                    redirect_snippet = ""
                    if resp_status is not None and 300 <= resp_status < 400:
                        loc = resp_headers.get("Location") or resp_headers.get("location")
                        if loc:
                            follow_url = loc if loc.startswith("http") else f"{self.base}{loc}"
                            async with self._request(
                                "GET",
                                follow_url,
                                timeout=5,
                            ) as redirect_resp:
                                redirected_base = self._base_from_url(redirect_resp.url)
                                if redirected_base:
                                    self._set_base(redirected_base)
                                redirect_snippet = await self._read_snippet(redirect_resp)

                    if not self._has_session_cookies() and self._looks_like_login_page(redirect_snippet):
                        raise SolarwattAuthError("Login returned to sign-in page without session cookie")

                    if not self._has_session_cookies():
                        self._log.debug(
                            "Login response delivered no reusable cookies. "
                            "Host=%s Base=%s Status=%s Content-Type=%s Username=%s",
                            self.host,
                            self.base,
                            resp_status,
                            resp_ct or "<none>",
                            username,
                        )

                    self._last_login = time.time()
                    self._log.debug("Successfully logged in to %s via %s", self.host, self.base)
                    return
                except SolarwattAuthError as err:
                    last_auth_error = err
                except SolarwattNotManagerError as err:
                    last_not_manager_error = err
                except Exception as e:
                    if isinstance(e, (ClientError, asyncio.TimeoutError)):
                        last_connection_error = SolarwattConnectionError(
                            f"Login connection error via {self.base}: {str(e)}"
                        )
                    elif isinstance(e, SolarwattConnectionError):
                        last_connection_error = e
                    else:
                        last_connection_error = SolarwattConnectionError(
                            f"Login error via {self.base}: {str(e)}"
                        )

        if last_auth_error is not None:
            raise last_auth_error
        if last_not_manager_error is not None:
            raise last_not_manager_error
        if last_connection_error is not None:
            raise last_connection_error
        raise SolarwattConnectionError("Login failed for unknown reasons")

    async def async_probe_manager(self) -> None:
        """Check whether the host looks like a SOLARWATT Manager."""
        last_connection_error: SolarwattConnectionError | None = None

        for base in self._candidate_bases:
            self._set_base(base)
            for path in ("/logon.html", "/", "/rest/"):
                url = f"{self.base}{path}"
                try:
                    async with self._request(
                        "GET",
                        url,
                        timeout=5,
                        allow_redirects=True,
                    ) as resp:
                        redirected_base = self._base_from_url(resp.url)
                        if redirected_base:
                            self._set_base(redirected_base)

                        if resp.status == 404 and path == "/logon.html":
                            continue

                        if 200 <= resp.status < 500:
                            snippet = await self._read_snippet(resp)
                            if (
                                "/auth/login" in snippet
                                or "kiwios-app-frame" in snippet
                                or resp.status in (401, 403)
                                or path == "/rest/"
                            ):
                                self._log.debug(
                                    "Detected SOLARWATT Manager on %s via %s",
                                    self.host,
                                    self.base,
                                )
                                return
                except (ClientError, asyncio.TimeoutError) as e:
                    last_connection_error = SolarwattConnectionError(
                        f"Probe failed via {self.base}: {e}"
                    )

        if last_connection_error is not None:
            raise last_connection_error
        raise SolarwattNotManagerError("No SOLARWATT Manager login page detected")

    async def _ensure_json(self, resp, where: str) -> Any:
        """Parse JSON with better diagnostics."""
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "json" not in ct:
            snippet = await self._read_snippet(resp)
            raise SolarwattProtocolError(
                f"Antwort ist kein JSON bei {where}. Status={resp.status}, Content-Type={ct or '<none>'}, "
                f"Cookies={self._cookie_debug()}, Snippet={snippet}"
            )
        return await resp.json()

    async def _ensure_session(self) -> None:
        if time.time() - self._last_login > self.session_ttl:
            await self.async_login()

    async def _async_get_json_endpoint(self, path: str, *, where: str) -> Any:
        """Fetch a JSON endpoint with one reauthentication retry on auth/HTML."""
        await self._ensure_session()

        for attempt in range(2):
            url = f"{self.base}{path}"
            async with self._request(
                "GET",
                url,
                timeout=5,
            ) as resp:
                redirected_base = self._base_from_url(resp.url)
                if redirected_base:
                    self._set_base(redirected_base)

                if resp.status in (401, 403):
                    if attempt == 0:
                        await self.async_login()
                        continue
                    resp.raise_for_status()

                ct = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" in ct and attempt == 0:
                    await self.async_login()
                    continue
                if "text/html" in ct:
                    snippet = await self._read_snippet(resp)
                    if self._looks_like_login_page(snippet):
                        raise SolarwattAuthError(f"Session expired while requesting {where}")

                resp.raise_for_status()
                return await self._ensure_json(resp, where)

    async def async_validate_connection(self) -> None:
        """Test connection to SOLARWATT Manager."""
        try:
            await self.async_login()
            await self.async_get_items()
        except SolarwattError:
            raise
        except Exception as e:
            raise SolarwattConnectionError(
                f"Cannot connect to SOLARWATT Manager: {str(e)}"
            ) from e

    async def async_get_items(self) -> list[dict[str, Any]]:
        try:
            return await self._async_get_json_endpoint(
                "/rest/items",
                where="GET /rest/items",
            )
        except SolarwattError:
            raise
        except ClientResponseError as e:
            self._log.error(f"HTTP error {e.status} fetching items from {self.host}")
            if e.status in (401, 403):
                raise SolarwattAuthError(f"HTTP {e.status} fetching items") from e
            if e.status == 404:
                raise SolarwattNotManagerError("Items endpoint not found") from e
            raise SolarwattConnectionError(f"HTTP error {e.status}") from e
        except (ClientError, asyncio.TimeoutError) as e:
            self._log.exception(f"Connection error fetching items from {self.host}: {e}")
            raise SolarwattConnectionError(str(e)) from e
        except Exception as e:
            self._log.exception(f"Unexpected error fetching items from {self.host}: {e}")
            raise SolarwattConnectionError(str(e)) from e

    async def async_get_things(self) -> list[dict[str, Any]]:
        try:
            return await self._async_get_json_endpoint(
                "/rest/things",
                where="GET /rest/things",
            )
        except SolarwattError:
            raise
        except ClientResponseError as e:
            if e.status in (401, 403):
                raise SolarwattAuthError("HTTP error fetching things") from e
            if e.status == 404:
                raise SolarwattProtocolError("Things endpoint not found") from e
            raise SolarwattConnectionError(f"HTTP error {e.status}") from e
        except (ClientError, asyncio.TimeoutError) as e:
            raise SolarwattConnectionError(f"Connection error fetching things: {e}") from e
        except Exception as e:
            raise SolarwattConnectionError(f"Error fetching things: {e}") from e
