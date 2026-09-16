from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from functools import partial
from typing import Any, NamedTuple

from aiohttp import ClientError, ClientResponseError, ClientSession, CookieJar
from homeassistant.helpers.update_coordinator import UpdateFailed

from .hems_client import (
    KiwiGridHEMSAuthError,
    KiwiGridHEMSClient,
    KiwiGridHEMSConnectionError,
    KiwiGridHEMSError,
    KiwiGridHEMSProtocolError,
    consumers_endpoint_to_items,
    energy_flow_endpoint_to_items,
    hems_device_names_by_id,
    hems_payloads_to_items,
    hems_payloads_to_things,
    is_analytics_payload,
    merge_analytics_aggregates,
    summary_anchor_time_window,
)
from .hems_api import (
    ENERGY_OVERVIEW_PATH,
    THINGS_PATH,
    energy_overview_to_items,
    hems_configurator_to_things,
    kiwigrid_flow_thing,
)


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


class SummaryAnchor(NamedTuple):
    """How one summary payload is assembled from its two halves."""

    period: str
    increment_key: str
    getter_name: str


HEMSEndpointGetter = Callable[[], Awaitable[Any]]
HEMS_STATS_HISTORY_REQUEST_TIMEOUT = 300
HEMS_SEQUENTIAL_RETRY_LIMIT = 4
HEMS_SUMMARY_ANCHORS: dict[str, SummaryAnchor] = {
    f"analytics_{kind}_{period}": SummaryAnchor(
        period,
        "analytics_finance" if kind == "finance" else f"analytics_{kind}_work_today",
        f"async_get_analytics_{kind}_{period}",
    )
    for kind in ("consumption", "production", "storage", "finance")
    for period in ("month", "year")
}
HEMS_DAILY_SUMMARIES = ("analytics_independence_month", "analytics_independence_year")
HEMS_YEAR_ANALYTICS_GETTERS: dict[str, str] = {
    "analytics_consumption_year": "async_get_analytics_consumption_year",
    "analytics_production_year": "async_get_analytics_production_year",
    "analytics_storage_year": "async_get_analytics_storage_year",
}


class SOLARWATTClient:
    def __init__(self, hass, host: str, username: str, password: str):
        if host and not isinstance(host, str):
            raise ValueError("host must be a string")
        if username and not isinstance(username, str):
            raise ValueError("username must be a string")
        if password and not isinstance(password, str):
            raise ValueError("password must be a string")

        self.hass = hass
        self.host = str(host or "").strip().lower()
        self.username = str(username or "")
        self.password = str(password or "")

        self._candidate_bases = (
            [f"http://{self.host}", f"https://{self.host}"] if self.host else []
        )
        self.base = self._candidate_bases[0] if self._candidate_bases else ""

        self._session = ClientSession(cookie_jar=CookieJar(unsafe=True))
        self.session_ttl = 900
        self._last_login = 0.0
        self._hems_client: KiwiGridHEMSClient | None = None
        self._hems_client_credentials: tuple[str, str] | None = None
        self._hems_payload_cache: dict[str, Any] = {}
        self._hems_daily_analytics_cache: dict[str, tuple[date, Any]] = {}
        self._hems_profile_updated_at: float | None = None
        self._hems_endpoint_errors: dict[str, str] = {}
        self.hems_partial_errors: tuple[str, ...] = ()
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

    def _get_hems_client(self, username: str, password: str) -> KiwiGridHEMSClient:
        """Return the reusable HEMS client for the current credentials."""
        credentials = (str(username or "").strip(), str(password or ""))
        if self._hems_client is not None and self._hems_client_credentials == credentials:
            return self._hems_client

        self._hems_client = KiwiGridHEMSClient(
            self._session,
            username=credentials[0],
            password=credentials[1],
        )
        self._hems_client_credentials = credentials
        self._hems_payload_cache.clear()
        self._hems_daily_analytics_cache.clear()
        self._hems_profile_updated_at = None
        self._hems_endpoint_errors.clear()
        self.hems_partial_errors = ()
        return self._hems_client

    async def async_login(self) -> None:
        if not self.host:
            raise SolarwattConnectionError("Local SOLARWATT host is not configured")
        if not self.username or not self.password:
            raise SolarwattAuthError("Local SOLARWATT credentials are not configured")

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
            await self.async_get_energy_overview_items()
        except SolarwattError:
            raise
        except Exception as e:
            raise SolarwattConnectionError(
                f"Cannot connect to SOLARWATT Manager: {str(e)}"
            ) from e

    async def async_get_energy_overview_items(self) -> list[dict[str, Any]]:
        try:
            payload = await self._async_get_json_endpoint(
                ENERGY_OVERVIEW_PATH,
                where=f"GET {ENERGY_OVERVIEW_PATH}",
            )
            if not isinstance(payload, dict):
                raise SolarwattProtocolError("HEMS energy overview response is not an object")

            items = energy_overview_to_items(payload)
            if not items:
                raise SolarwattProtocolError("HEMS energy overview contains no supported values")
            return items
        except SolarwattError:
            raise
        except ClientResponseError as e:
            if e.status in (401, 403):
                raise SolarwattAuthError("HTTP error fetching HEMS energy overview") from e
            if e.status == 404:
                raise SolarwattNotManagerError("HEMS energy overview endpoint not found") from e
            raise SolarwattConnectionError(f"HTTP error {e.status} fetching HEMS energy overview") from e
        except (ClientError, asyncio.TimeoutError) as e:
            raise SolarwattConnectionError(f"Connection error fetching HEMS energy overview: {e}") from e

    async def async_get_hems_configurator_things(self) -> list[dict[str, Any]]:
        """Fetch local HEMS configurator things from the SOLARWATT Manager."""
        try:
            payload = await self._async_get_json_endpoint(
                THINGS_PATH,
                where=f"GET {THINGS_PATH}",
            )
            if not isinstance(payload, list):
                raise SolarwattProtocolError("HEMS things response is not a list")
            return hems_configurator_to_things(payload)
        except SolarwattError:
            raise
        except ClientResponseError as e:
            if e.status in (401, 403):
                raise SolarwattAuthError("HTTP error fetching HEMS things") from e
            if e.status == 404:
                raise SolarwattProtocolError("HEMS things endpoint not found") from e
            raise SolarwattConnectionError(f"HTTP error {e.status} fetching HEMS things") from e
        except (ClientError, asyncio.TimeoutError) as e:
            raise SolarwattConnectionError(f"Connection error fetching HEMS things: {e}") from e

    async def async_get_hems_items(
        self,
        *,
        username: str = "",
        password: str = "",
        include_energy_flow: bool = False,
        refresh_devices: bool = True,
        refresh_statistics: bool = True,
        profile_cache_interval: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch supported KiwiGrid HEMS data and convert it to item records."""
        hems = self._get_hems_client(username, password)
        status_items: list[dict[str, Any]] = []

        def _hems_status_item(name: str, state: str) -> dict[str, Any]:
            return {
                "name": f"hems_{name}",
                "label": name.replace("_", " ").title(),
                "state": state,
                "type": "String",
                "editable": False,
                "category": "kiwigrid_hems",
            }

        def _hems_count_item(count: int) -> dict[str, Any]:
            return {
                "name": "hems_item_count",
                "label": "HEMS Item Count",
                "state": str(count),
                "type": "Number",
                "editable": False,
                "category": "kiwigrid_hems",
            }

        if not hems.enabled:
            return [
                _hems_status_item("status", "disabled"),
                _hems_count_item(0),
            ]

        self.hems_partial_errors = ()
        payloads, errors, successful_requests = await self._async_fetch_hems_payloads(
            hems,
            collect_errors=True,
            include_energy_flow=include_energy_flow,
            refresh_devices=refresh_devices,
            refresh_statistics=refresh_statistics,
            profile_cache_interval=profile_cache_interval,
        )
        self.hems_partial_errors = tuple(errors)
        if errors and successful_requests == 0:
            raise SolarwattConnectionError(
                "All requested KiwiGrid HEMS endpoints failed: " + "; ".join(errors)
            )

        hems_items = hems_payloads_to_items(**payloads)
        status_items.append(_hems_status_item("status", "ok" if hems_items else "empty"))
        status_items.append(_hems_count_item(len(hems_items)))
        if errors:
            status_items.append(_hems_status_item("last_error", " | ".join(errors)[:250]))
        return status_items + hems_items

    async def async_get_hems_energy_flow_items(
        self,
        *,
        username: str = "",
        password: str = "",
    ) -> list[dict[str, Any]]:
        """Fetch live KiwiGrid HEMS energy-flow values as KiwiGrid Flow items."""
        hems = self._get_hems_client(username, password)
        if not hems.enabled:
            return []

        try:
            payload = await hems.async_get_energy_flow()
            self._hems_payload_cache["energy_flow"] = payload
            self._hems_endpoint_errors.pop("energy_flow", None)
        except KiwiGridHEMSAuthError as err:
            raise SolarwattAuthError(f"KiwiGrid HEMS authentication failed: {err}") from err
        except (KiwiGridHEMSProtocolError, KiwiGridHEMSConnectionError) as err:
            raise SolarwattConnectionError(f"KiwiGrid HEMS energy flow failed: {err}") from err
        except KiwiGridHEMSError as err:
            raise SolarwattConnectionError(f"KiwiGrid HEMS energy flow failed: {err}") from err

        try:
            consumers = await hems.async_get_home_consumption_consumers()
            self._hems_payload_cache["home_consumption_consumers"] = consumers
            self._hems_endpoint_errors.pop("home_consumption_consumers", None)
        except KiwiGridHEMSAuthError as err:
            raise SolarwattAuthError(f"KiwiGrid HEMS authentication failed: {err}") from err
        except KiwiGridHEMSError as err:
            self._log.debug(
                "KiwiGrid HEMS consumer consumption unavailable for energy flow: %s",
                err,
            )
            consumers = self._hems_payload_cache.get(
                "home_consumption_consumers",
                [],
            )

        name_payloads = {
            key: self._hems_payload_cache.get(key, [])
            for key in (
                "devices",
                "device_optimizations",
                "batteries",
                "pv_plants",
                "evstations",
                "plugs",
                "smart_heaters",
            )
        }

        return energy_flow_endpoint_to_items(
            payload,
            device_names_by_id=hems_device_names_by_id(**name_payloads),
        ) + consumers_endpoint_to_items(consumers)

    async def async_calculate_hems_stats_total_value(
        self,
        item_name: str,
        *,
        username: str = "",
        password: str = "",
        max_years: int = 20,
        history_cache: dict[tuple[str, int], dict[str, Any]] | None = None,
    ) -> tuple[float, list[int]]:
        """Calculate a stats offset by summing available completed historic years."""
        payload_key = _hems_year_payload_key_for_item(item_name)
        getter_name = HEMS_YEAR_ANALYTICS_GETTERS.get(payload_key)
        if getter_name is None:
            raise SolarwattProtocolError(f"Unsupported KiwiGrid stats item: {item_name}")

        hems = KiwiGridHEMSClient(
            self._session,
            username=username,
            password=password,
            request_timeout=HEMS_STATS_HISTORY_REQUEST_TIMEOUT,
        )
        if not hems.enabled:
            raise SolarwattAuthError("KiwiGrid HEMS credentials are missing")

        getter = getattr(hems, getter_name)
        current_year = datetime.now().astimezone().year
        offset = 0.0
        years: list[int] = []
        payload_cache = history_cache if history_cache is not None else {}
        for year in _completed_previous_years(current_year, max_years):
            try:
                cache_key = (payload_key, year)
                if cache_key in payload_cache:
                    payload = payload_cache[cache_key]
                else:
                    payload = await getter(
                        from_time=datetime(year, 1, 1, 0, 0, 0),
                        to_time=datetime(year, 12, 31, 23, 59, 59),
                    )
                    payload_cache[cache_key] = payload
            except KiwiGridHEMSAuthError as err:
                raise SolarwattAuthError(f"KiwiGrid HEMS authentication failed: {err}") from err
            except (KiwiGridHEMSProtocolError, KiwiGridHEMSConnectionError) as err:
                raise SolarwattConnectionError(
                    f"KiwiGrid HEMS stats history failed: {err}"
                ) from err
            except KiwiGridHEMSError as err:
                raise SolarwattConnectionError(
                    f"KiwiGrid HEMS stats history failed: {err}"
                ) from err

            value = _hems_stats_item_value(payload_key, item_name, payload)
            if value is None:
                break
            offset += value
            years.append(year)

        if not years:
            raise SolarwattProtocolError(
                f"No KiwiGrid stats history values found for {item_name}"
            )
        return offset, years

    async def async_get_hems_things(
        self,
        *,
        username: str = "",
        password: str = "",
        include_energy_flow: bool = False,
        use_cached: bool = False,
        profile_cache_interval: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch supported KiwiGrid HEMS data and convert it to thing records."""
        hems = self._get_hems_client(username, password)
        if not hems.enabled:
            return []

        if use_cached and self._hems_payload_cache:
            payloads = dict(self._hems_payload_cache)
        else:
            payloads, _errors, _successful_requests = await self._async_fetch_hems_payloads(
                hems,
                collect_errors=False,
                include_energy_flow=include_energy_flow,
                profile_cache_interval=profile_cache_interval,
            )

        things = hems_payloads_to_things(**payloads)
        if include_energy_flow:
            existing_uids = {
                str(thing.get("UID") or thing.get("uid") or "") for thing in things
            }
            thing = kiwigrid_flow_thing()
            thing_uid = str(thing.get("UID") or thing.get("uid") or "")
            if thing_uid and thing_uid not in existing_uids:
                things.append(thing)
        return things

    async def _async_fetch_hems_payloads(
        self,
        hems: KiwiGridHEMSClient,
        *,
        collect_errors: bool,
        include_energy_flow: bool = False,
        refresh_devices: bool = True,
        refresh_statistics: bool = True,
        profile_cache_interval: int = 0,
    ) -> tuple[dict[str, Any], list[str], int]:
        """Fetch all supported KiwiGrid HEMS endpoint payloads."""
        payloads: dict[str, Any] = {
            key: payload
            for key, payload in self._hems_payload_cache.items()
            if include_energy_flow
            or key not in {"energy_flow", "home_consumption_consumers"}
        }
        successful_requests = 0
        semaphore = asyncio.Semaphore(4)
        profile_cached = (
            self._hems_profile_updated_at is not None
            and time.monotonic() - self._hems_profile_updated_at < profile_cache_interval
            and "user_profile" in self._hems_payload_cache
        )
        poll_now = datetime.now().astimezone()
        cache_hits: set[str] = set()

        if hems.enabled:
            try:
                await hems.async_ensure_authenticated()
            except KiwiGridHEMSAuthError as err:
                raise SolarwattAuthError(
                    f"KiwiGrid HEMS authentication failed: {err}"
                ) from err
            except KiwiGridHEMSError as err:
                raise SolarwattConnectionError(
                    f"KiwiGrid HEMS authentication failed: {err}"
                ) from err

        async def _fetch_endpoint(
            key: str,
            getter: HEMSEndpointGetter,
        ) -> tuple[str, Any | None, KiwiGridHEMSError | None]:
            async with semaphore:
                try:
                    return key, await getter(), None
                except KiwiGridHEMSError as err:
                    return key, None, err

        endpoint_getters = self._with_daily_analytics_getters(
            hems,
            self._hems_endpoint_getters(
                hems,
                include_energy_flow=include_energy_flow,
            ),
            poll_now,
            cache_hits,
        )
        scheduled_getters: list[tuple[str, HEMSEndpointGetter]] = []
        for key, getter in endpoint_getters:
            match key:
                case "user_profile":
                    due = not profile_cached
                case "energy_flow" | "home_consumption_consumers":
                    due = include_energy_flow
                case _:
                    due = refresh_statistics if key.startswith("analytics_") else refresh_devices
            if due:
                scheduled_getters.append((key, getter))
        endpoint_getters = tuple(scheduled_getters)
        getters_by_key = dict(endpoint_getters)
        results = list(await asyncio.gather(
            *(
                _fetch_endpoint(key, getter)
                for key, getter in endpoint_getters
            )
        ))

        retry_candidates = [
            (index, key, getters_by_key[key])
            for index, (key, _payload, error) in enumerate(results)
            if isinstance(error, KiwiGridHEMSConnectionError)
        ]
        if 0 < len(retry_candidates) <= HEMS_SEQUENTIAL_RETRY_LIMIT:
            for index, key, getter in retry_candidates:
                try:
                    results[index] = (key, await getter(), None)
                except KiwiGridHEMSError as err:
                    results[index] = (key, None, err)
        elif retry_candidates:
            self._log.debug(
                "Skipping sequential KiwiGrid HEMS retries because %s endpoints "
                "failed in the same poll",
                len(retry_candidates),
            )

        resolved_keys: set[str] = set()
        for key, payload, error in results:
            if (
                error is None
                and any(
                    key == anchor.increment_key
                    for anchor in HEMS_SUMMARY_ANCHORS.values()
                )
                and not is_analytics_payload(payload)
            ):
                error = KiwiGridHEMSProtocolError(
                    "Summary increment returned a malformed analytics payload"
                )
            if error is None:
                payloads[key] = payload
                if key not in HEMS_SUMMARY_ANCHORS:
                    self._hems_payload_cache[key] = payload
                resolved_keys.add(key)
                self._hems_endpoint_errors.pop(key, None)
                if key == "user_profile":
                    self._hems_profile_updated_at = time.monotonic()
                successful_requests += 1
                continue
            if isinstance(error, KiwiGridHEMSAuthError):
                raise SolarwattAuthError(
                    f"KiwiGrid HEMS authentication failed: {error}"
                ) from error
            self._log.debug(
                "KiwiGrid HEMS endpoint %s could not be fetched: %s",
                key,
                error,
            )
            self._hems_endpoint_errors[key] = f"{key}: {error}"
            payloads[key] = self._hems_payload_cache.get(key, [])

        # Cached or empty-period responses prove nothing about portal availability.
        successful_requests -= len(cache_hits & resolved_keys)
        self._apply_summary_anchors(payloads, resolved_keys, poll_now)
        errors = list(self._hems_endpoint_errors.values()) if collect_errors else []
        return payloads, errors, successful_requests

    def _with_daily_analytics_getters(
        self,
        hems: KiwiGridHEMSClient,
        endpoint_getters: tuple[tuple[str, HEMSEndpointGetter], ...],
        poll_now: datetime,
        cache_hits: set[str],
    ) -> tuple[tuple[str, HEMSEndpointGetter], ...]:
        """Cache completed-day totals and server-calculated ratios daily."""
        poll_day = poll_now.date()
        getters: list[tuple[str, HEMSEndpointGetter]] = []
        for key, getter in endpoint_getters:
            request_getter: HEMSEndpointGetter | None = getter
            if anchor := HEMS_SUMMARY_ANCHORS.get(key):
                window = summary_anchor_time_window(anchor.period, now=poll_now)
                request_getter = (
                    partial(
                        getattr(hems, anchor.getter_name),
                        from_time=window[0],
                        to_time=window[1],
                    )
                    if window is not None else None
                )
            elif key not in HEMS_DAILY_SUMMARIES:
                getters.append((key, getter))
                continue
            getters.append((key, partial(
                self._async_get_daily_analytics,
                key,
                request_getter,
                poll_day,
                cache_hits,
            )))
        return tuple(getters)

    async def _async_get_daily_analytics(
        self,
        key: str,
        getter: HEMSEndpointGetter | None,
        poll_day: date,
        cache_hits: set[str],
    ) -> Any:
        """Reuse a daily response or fetch and validate it before caching.

        A missing getter denotes the first day of a period, with no completed
        days to request. Cache dates always identify the poll's calendar day.
        """
        if getter is None:
            cache_hits.add(key)
            return None
        cached_day, payload = self._hems_daily_analytics_cache.get(key, (None, None))
        if cached_day == poll_day:
            cache_hits.add(key)
            return payload
        payload = await getter()
        if not is_analytics_payload(payload):
            raise KiwiGridHEMSProtocolError(
                f"{key} returned a malformed analytics payload"
            )
        self._hems_daily_analytics_cache[key] = (poll_day, payload)
        return payload

    def _apply_summary_anchors(
        self,
        payloads: dict[str, Any],
        resolved_keys: set[str],
        poll_now: datetime,
    ) -> None:
        """Publish the summary totals as completed days plus today.

        Both halves have to be fresh and to belong to the same day. If either
        is missing, or the day rolled over while the poll was running, the
        previous total is published again rather than one that lost a half.
        """
        same_day = datetime.now().astimezone().date() == poll_now.date()
        for key, anchor in HEMS_SUMMARY_ANCHORS.items():
            if same_day and resolved_keys.issuperset({key, anchor.increment_key}):
                merged = merge_analytics_aggregates(
                    payloads.get(key),
                    payloads.get(anchor.increment_key),
                )
                if merged is not None:
                    self._hems_payload_cache[key] = merged
            payloads[key] = self._hems_payload_cache.get(key, [])

    @staticmethod
    def _hems_endpoint_getters(
        hems: KiwiGridHEMSClient,
        *,
        include_energy_flow: bool = False,
    ) -> tuple[tuple[str, HEMSEndpointGetter], ...]:
        """Return the supported KiwiGrid HEMS endpoints in fetch order."""
        getters: tuple[tuple[str, HEMSEndpointGetter], ...] = (
            ("batteries", hems.async_get_battery),
            ("devices", hems.async_get_devices),
            ("device_optimizations", hems.async_get_device_optimizations),
            ("pv_plants", hems.async_get_pv_plants),
            ("evstations", hems.async_get_evstations),
            ("plugs", hems.async_get_plugs),
            ("smart_heaters", hems.async_get_smart_heaters),
            ("analytics_consumption", hems.async_get_analytics_consumption),
            ("analytics_production", hems.async_get_analytics_production),
            ("analytics_production_work_today", hems.async_get_analytics_production_work_today),
            ("analytics_storage_work_today", hems.async_get_analytics_storage_work_today),
            (
                "analytics_consumption_work_today",
                hems.async_get_analytics_consumption_work_today,
            ),
            ("analytics_consumption_month", hems.async_get_analytics_consumption_month),
            ("analytics_production_month", hems.async_get_analytics_production_month),
            ("analytics_consumption_year", hems.async_get_analytics_consumption_year),
            ("analytics_production_year", hems.async_get_analytics_production_year),
            ("analytics_storage", hems.async_get_analytics_storage),
            ("analytics_storage_month", hems.async_get_analytics_storage_month),
            ("analytics_storage_year", hems.async_get_analytics_storage_year),
            ("analytics_independence", hems.async_get_analytics_independence),
            (
                "analytics_independence_month",
                hems.async_get_analytics_independence_month,
            ),
            (
                "analytics_independence_year",
                hems.async_get_analytics_independence_year,
            ),
            ("analytics_finance", hems.async_get_analytics_finance),
            ("analytics_finance_month", hems.async_get_analytics_finance_month),
            ("analytics_finance_year", hems.async_get_analytics_finance_year),
            ("user_profile", hems.async_get_user_profile),
        )
        if include_energy_flow:
            getters = getters[:7] + (
                ("energy_flow", hems.async_get_energy_flow),
                (
                    "home_consumption_consumers",
                    hems.async_get_home_consumption_consumers,
                ),
            ) + getters[7:]
        return getters

    async def async_set_hems_device_optimization_mode(
        self,
        device_id: str,
        optimization_mode: str,
        *,
        username: str = "",
        password: str = "",
    ) -> None:
        """Set the optimization mode for one KiwiGrid HEMS device."""
        hems = self._get_hems_client(username, password)
        if not hems.enabled:
            raise SolarwattAuthError("KiwiGrid HEMS credentials are missing")
        try:
            await hems.async_set_device_optimization_mode(device_id, optimization_mode)
        except KiwiGridHEMSAuthError as err:
            raise SolarwattAuthError(f"KiwiGrid HEMS authentication failed: {err}") from err
        except KiwiGridHEMSError as err:
            raise SolarwattConnectionError(f"KiwiGrid HEMS device update failed: {err}") from err

    async def async_set_hems_device_optimization_state(
        self,
        device_id: str,
        target_state: str,
        *,
        username: str = "",
        password: str = "",
    ) -> None:
        """Switch one KiwiGrid HEMS optimizable device on or off."""
        hems = self._get_hems_client(username, password)
        if not hems.enabled:
            raise SolarwattAuthError("KiwiGrid HEMS credentials are missing")
        try:
            await hems.async_set_device_optimization_state(device_id, target_state)
        except KiwiGridHEMSAuthError as err:
            raise SolarwattAuthError(f"KiwiGrid HEMS authentication failed: {err}") from err
        except KiwiGridHEMSError as err:
            raise SolarwattConnectionError(f"KiwiGrid HEMS device switch failed: {err}") from err

    async def async_get_things(self) -> list[dict[str, Any]]:
        """Fetch local thing metadata from the HEMS configurator endpoint."""
        return await self.async_get_hems_configurator_things()


def _hems_year_payload_key_for_item(item_name: str) -> str:
    name = str(item_name or "").strip().lower()
    for payload_key in HEMS_YEAR_ANALYTICS_GETTERS:
        if name.startswith(f"hems_{payload_key}_"):
            return payload_key
    raise SolarwattProtocolError(f"Unsupported KiwiGrid stats item: {item_name}")


def _hems_stats_item_value(
    payload_key: str,
    item_name: str,
    payload: dict[str, Any],
) -> float | None:
    payloads: dict[str, Any] = {payload_key: payload}
    items = hems_payloads_to_items(**payloads)
    for item in items:
        if item.get("name") != item_name:
            continue
        return _numeric_state_value(item.get("state"))
    return None


def _numeric_state_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text or text.upper() == "NULL":
        return None
    try:
        return float(text.split()[0])
    except (IndexError, TypeError, ValueError):
        return None


def _completed_previous_years(current_year: int, max_years: int) -> range:
    """Return completed previous years, newest first."""
    return range(current_year - 1, current_year - max(max_years, 1) - 1, -1)
