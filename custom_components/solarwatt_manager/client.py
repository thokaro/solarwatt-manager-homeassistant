from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
import struct
import time
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, CookieJar
from homeassistant.helpers.update_coordinator import UpdateFailed

from .hems_api import (
    ENERGY_OVERVIEW_PATH,
    THINGS_PATH,
    battery_soc_to_legacy_items,
    energy_overview_to_items,
    energy_overview_to_legacy_items,
    extended_modbus_to_legacy_items,
    things_to_openhab_things,
)

_FOXESS_BATTERY_SOC_ADDRESSES = (37612, 31024, 31038, 38310)
_MODBUS_READ_HOLDING_REGISTERS = 3
_MODBUS_READ_INPUT_REGISTERS = 4


@dataclass(frozen=True)
class _ModbusCandidate:
    addresses: tuple[int, ...]
    scale: float = 1.0
    signed: bool = False
    min_value: float | None = None
    max_value: float | None = None
    transform: Callable[[int], int | float | str] | None = None


@dataclass(frozen=True)
class _ModbusSensorSpec:
    key: str
    candidates: tuple[_ModbusCandidate, ...]


def _candidate(
    *addresses: int,
    scale: float = 1.0,
    signed: bool = False,
    min_value: float | None = None,
    max_value: float | None = None,
    transform: Callable[[int], int | float | str] | None = None,
) -> _ModbusCandidate:
    return _ModbusCandidate(
        tuple(addresses),
        scale=scale,
        signed=signed,
        min_value=min_value,
        max_value=max_value,
        transform=transform,
    )


def _cell_voltage(raw: int) -> float:
    return raw / 1000 if raw >= 1000 else raw * 0.1


def _normal_work_mode_name(code: int) -> str:
    return {
        0: "Self Use",
        1: "Feed-in First",
        2: "Back-up",
        4: "Peak Shaving",
    }.get(code, f"Unknown ({code})")


def _h3_pro_work_mode_name(code: int) -> str:
    return {
        1: "Self Use",
        2: "Feed-in First",
        3: "Back-up",
        4: "Peak Shaving",
    }.get(code, f"Unknown ({code})")


_EXTENDED_MODBUS_SPECS: tuple[_ModbusSensorSpec, ...] = (
    _ModbusSensorSpec(
        "solar_energy_total",
        (
            _candidate(39602, 39601, scale=0.01, min_value=0),
            _candidate(32001, 32000, scale=0.1, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "solar_energy_today",
        (
            _candidate(39604, 39603, scale=0.01, min_value=0, max_value=1000),
            _candidate(32002, scale=0.1, min_value=0, max_value=1000),
        ),
    ),
    _ModbusSensorSpec(
        "battery_charge_total",
        (
            _candidate(39606, 39605, scale=0.01, min_value=0),
            _candidate(32004, 32003, scale=0.1, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "battery_charge_today",
        (
            _candidate(39608, 39607, scale=0.01, min_value=0, max_value=1000),
            _candidate(32005, scale=0.1, min_value=0, max_value=1000),
        ),
    ),
    _ModbusSensorSpec(
        "battery_discharge_total",
        (
            _candidate(39610, 39609, scale=0.01, min_value=0),
            _candidate(32007, 32006, scale=0.1, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "battery_discharge_today",
        (
            _candidate(39612, 39611, scale=0.01, min_value=0, max_value=1000),
            _candidate(32008, scale=0.1, min_value=0, max_value=1000),
        ),
    ),
    _ModbusSensorSpec(
        "feed_in_energy_total",
        (
            _candidate(39614, 39613, scale=0.01, min_value=0),
            _candidate(32010, 32009, scale=0.1, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "feed_in_energy_today",
        (
            _candidate(39616, 39615, scale=0.01, min_value=0, max_value=1000),
            _candidate(32011, scale=0.1, min_value=0, max_value=1000),
        ),
    ),
    _ModbusSensorSpec(
        "grid_consumption_energy_total",
        (
            _candidate(39618, 39617, scale=0.01, min_value=0),
            _candidate(32013, 32012, scale=0.1, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "grid_consumption_energy_today",
        (
            _candidate(39620, 39619, scale=0.01, min_value=0, max_value=1000),
            _candidate(32014, scale=0.1, min_value=0, max_value=1000),
        ),
    ),
    _ModbusSensorSpec(
        "total_yield_total",
        (
            _candidate(39622, 39621, scale=0.01, min_value=0),
            _candidate(32016, 32015, scale=0.1, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "total_yield_today",
        (
            _candidate(39624, 39623, scale=0.01, min_value=-200, max_value=200),
            _candidate(32017, scale=0.1, min_value=-200, max_value=200),
        ),
    ),
    _ModbusSensorSpec(
        "input_energy_total",
        (
            _candidate(39626, 39625, scale=0.01, min_value=0),
            _candidate(32019, 32018, scale=0.1, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "input_energy_today",
        (
            _candidate(39628, 39627, scale=0.01, min_value=-1000, max_value=1000),
            _candidate(32020, scale=0.1, min_value=-1000, max_value=1000),
        ),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_voltage",
        (
            _candidate(37609, scale=0.1, min_value=100, max_value=600),
            _candidate(31034, scale=0.1, min_value=100, max_value=600),
        ),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_current",
        (
            _candidate(37610, scale=0.1, signed=True, min_value=-100, max_value=100),
            _candidate(31035, scale=0.1, signed=True, min_value=-100, max_value=100),
        ),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_temperature",
        (
            _candidate(37611, scale=0.1, signed=True, min_value=-50, max_value=100),
            _candidate(31037, scale=0.1, signed=True, min_value=-50, max_value=100),
        ),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_soh",
        (
            _candidate(37624, min_value=0, max_value=100),
            _candidate(31090, min_value=0, max_value=100),
        ),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_cell_temperature_high",
        (_candidate(37617, scale=0.1, signed=True, min_value=-50, max_value=100),),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_cell_temperature_low",
        (_candidate(37618, scale=0.1, signed=True, min_value=-50, max_value=100),),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_cell_voltage_high",
        (_candidate(37619, min_value=0, max_value=5, transform=_cell_voltage),),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_cell_voltage_low",
        (_candidate(37620, min_value=0, max_value=5, transform=_cell_voltage),),
    ),
    _ModbusSensorSpec(
        "battery_bms_1_kwh_remaining",
        (_candidate(37632, scale=0.01, min_value=0),),
    ),
    _ModbusSensorSpec(
        "bms_1_connect_state",
        (_candidate(37002, min_value=0, max_value=10),),
    ),
    _ModbusSensorSpec(
        "inverter_temperature",
        (
            _candidate(39141, scale=0.1, signed=True, min_value=-50, max_value=100),
            _candidate(31032, scale=0.1, signed=True, min_value=-50, max_value=100),
        ),
    ),
    _ModbusSensorSpec(
        "inverter_state_code",
        (
            _candidate(39063, min_value=0),
            _candidate(31041, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "inverter_fault_1_code",
        (
            _candidate(39067, min_value=0),
            _candidate(31044, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "inverter_fault_2_code",
        (
            _candidate(39068, min_value=0),
            _candidate(31045, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "inverter_fault_3_code",
        (
            _candidate(39069, min_value=0),
            _candidate(31046, min_value=0),
        ),
    ),
    _ModbusSensorSpec(
        "work_mode_code",
        (
            _candidate(49203, min_value=0, max_value=10),
            _candidate(41000, min_value=0, max_value=10),
        ),
    ),
    _ModbusSensorSpec(
        "work_mode",
        (
            _candidate(49203, transform=_h3_pro_work_mode_name),
            _candidate(41000, transform=_normal_work_mode_name),
        ),
    ),
    _ModbusSensorSpec(
        "max_charge_current",
        (
            _candidate(46607, scale=0.1, min_value=0, max_value=200),
            _candidate(41007, scale=0.1, min_value=0, max_value=200),
        ),
    ),
    _ModbusSensorSpec(
        "max_discharge_current",
        (
            _candidate(46608, scale=0.1, min_value=0, max_value=200),
            _candidate(41008, scale=0.1, min_value=0, max_value=200),
        ),
    ),
    _ModbusSensorSpec(
        "min_soc",
        (
            _candidate(46609, min_value=0, max_value=100),
            _candidate(41009, min_value=0, max_value=100),
        ),
    ),
    _ModbusSensorSpec(
        "max_soc",
        (
            _candidate(46610, min_value=0, max_value=100),
            _candidate(41010, min_value=0, max_value=100),
        ),
    ),
    _ModbusSensorSpec(
        "min_soc_on_grid",
        (
            _candidate(46611, min_value=0, max_value=100),
            _candidate(41011, min_value=0, max_value=100),
        ),
    ),
    _ModbusSensorSpec(
        "import_power_limit",
        (_candidate(46502, 46501, min_value=0, max_value=99999),),
    ),
    _ModbusSensorSpec(
        "export_power_limit",
        (_candidate(46617, 46616, min_value=0, max_value=99999),),
    ),
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
        self._extended_modbus_candidate_cache: dict[str, int] = {}

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

    async def async_get_energy_overview_items(
        self,
        *,
        include_extended_modbus: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            payload = await self._async_get_json_endpoint(
                ENERGY_OVERVIEW_PATH,
                where=f"GET {ENERGY_OVERVIEW_PATH}",
            )
            if not isinstance(payload, dict):
                raise SolarwattProtocolError("Energy overview response is not an object")

            items = energy_overview_to_items(payload)
            try:
                things = await self._async_get_json_endpoint(
                    THINGS_PATH,
                    where=f"GET {THINGS_PATH}",
                )
                if isinstance(things, list):
                    legacy_items = energy_overview_to_legacy_items(payload, things)
                    existing_names = {item.get("name") for item in items}
                    items.extend(
                        item
                        for item in legacy_items
                        if item.get("name") not in existing_names
                    )
                    if (soc := await self.async_get_hems_battery_soc(things)) is not None:
                        existing_names.update(item.get("name") for item in items)
                        items.extend(
                            item
                            for item in battery_soc_to_legacy_items(things, soc)
                            if item.get("name") not in existing_names
                        )
                    if include_extended_modbus:
                        modbus_values = await self.async_get_hems_extended_modbus_values(things)
                        existing_names.update(item.get("name") for item in items)
                        items.extend(
                            item
                            for item in extended_modbus_to_legacy_items(things, modbus_values)
                            if item.get("name") not in existing_names
                        )
            except SolarwattError as err:
                self._log.debug("Unable to build legacy HEMS item aliases: %s", err)

            if not items:
                raise SolarwattProtocolError("Energy overview response contains no supported values")
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

    async def async_get_hems_things(self) -> list[dict[str, Any]]:
        try:
            payload = await self._async_get_json_endpoint(
                THINGS_PATH,
                where=f"GET {THINGS_PATH}",
            )
            if not isinstance(payload, list):
                raise SolarwattProtocolError("HEMS things response is not a list")
            return things_to_openhab_things(payload)
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

    async def async_get_hems_battery_soc(self, things: list[Any]) -> int | None:
        connection = _hems_modbus_connection(things)
        if connection is None:
            return None

        host, port, unit = connection
        valid_values: list[int] = []
        for address in _FOXESS_BATTERY_SOC_ADDRESSES:
            for function in (
                _MODBUS_READ_HOLDING_REGISTERS,
                _MODBUS_READ_INPUT_REGISTERS,
            ):
                try:
                    value = await _async_read_modbus_register(
                        host,
                        port,
                        unit,
                        function,
                        address,
                    )
                except Exception as err:
                    self._log.debug(
                        "Unable to read battery SoC via Modbus %s:%s unit %s address %s function %s: %s",
                        host,
                        port,
                        unit,
                        address,
                        function,
                        err,
                    )
                    continue

                if 0 <= value <= 100:
                    valid_values.append(value)

        for value in valid_values:
            if value > 0:
                return value
        return valid_values[0] if valid_values else None

    async def async_get_hems_extended_modbus_values(self, things: list[Any]) -> dict[str, Any]:
        connection = _hems_modbus_connection(things)
        if connection is None:
            return {}

        host, port, unit = connection
        values: dict[str, Any] = {}
        try:
            async with _ModbusTcpReader(host, port, unit) as reader:
                for spec in _EXTENDED_MODBUS_SPECS:
                    if (value := await self._async_read_extended_modbus_value(reader, spec)) is not None:
                        values[spec.key] = value
        except Exception as err:
            self._log.debug(
                "Unable to read extended Modbus data from %s:%s unit %s: %s",
                host,
                port,
                unit,
                err,
            )
            return values

        _add_derived_modbus_values(values)
        return values

    async def _async_read_extended_modbus_value(
        self,
        reader: "_ModbusTcpReader",
        spec: _ModbusSensorSpec,
    ) -> int | float | str | None:
        cached_index = self._extended_modbus_candidate_cache.get(spec.key)
        candidate_indexes = list(range(len(spec.candidates)))
        if cached_index in candidate_indexes:
            candidate_indexes.remove(cached_index)
            candidate_indexes.insert(0, cached_index)

        for index in candidate_indexes:
            candidate = spec.candidates[index]
            try:
                registers = [
                    await reader.read_register(_MODBUS_READ_HOLDING_REGISTERS, address)
                    for address in candidate.addresses
                ]
                value = _decode_modbus_candidate(candidate, registers)
            except Exception as err:
                self._log.debug(
                    "Unable to read extended Modbus key %s at %s: %s",
                    spec.key,
                    ",".join(str(address) for address in candidate.addresses),
                    err,
                )
                continue

            if value is None:
                continue
            self._extended_modbus_candidate_cache[spec.key] = index
            return value
        return None

    async def async_get_items(
        self,
        *,
        include_extended_modbus: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            return await self._async_get_json_endpoint(
                "/rest/items",
                where="GET /rest/items",
            )
        except SolarwattError:
            raise
        except ClientResponseError as e:
            if e.status in (401, 403):
                raise SolarwattAuthError(f"HTTP {e.status} fetching items") from e
            if e.status == 404:
                self._log.debug(
                    "Legacy /rest/items endpoint not found on %s; trying HEMS energy overview",
                    self.host,
                )
                return await self.async_get_energy_overview_items(
                    include_extended_modbus=include_extended_modbus,
                )
            self._log.error(f"HTTP error {e.status} fetching items from {self.host}")
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
                self._log.debug(
                    "Legacy /rest/things endpoint not found on %s; trying HEMS things",
                    self.host,
                )
                return await self.async_get_hems_things()
            raise SolarwattConnectionError(f"HTTP error {e.status}") from e
        except (ClientError, asyncio.TimeoutError) as e:
            raise SolarwattConnectionError(f"Connection error fetching things: {e}") from e
        except Exception as e:
            raise SolarwattConnectionError(f"Error fetching things: {e}") from e


def _hems_modbus_connection(things: list[Any]) -> tuple[str, int, int] | None:
    for thing in things:
        if not isinstance(thing, dict):
            continue
        config = thing.get("config")
        if not isinstance(config, dict):
            continue
        host = str(config.get("host") or "").strip()
        if not host:
            continue
        try:
            port = int(config.get("port") or 502)
            unit = int(config.get("unitId") or 247)
        except (TypeError, ValueError):
            continue
        return host, port, unit
    return None


class _ModbusTcpReader:
    def __init__(self, host: str, port: int, unit: int) -> None:
        self.host = host
        self.port = port
        self.unit = unit
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._transaction_id = 0
        self._cache: dict[tuple[int, int], int] = {}

    async def __aenter__(self) -> "_ModbusTcpReader":
        await self._connect()
        return self

    async def __aexit__(self, *_args) -> None:
        await self.close()

    async def _connect(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=3,
        )

    async def close(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def read_register(self, function: int, address: int) -> int:
        cache_key = (function, address)
        if cache_key in self._cache:
            return self._cache[cache_key]

        await self._connect()
        assert self._reader is not None
        assert self._writer is not None

        self._transaction_id = (self._transaction_id + 1) & 0xFFFF
        transaction_id = self._transaction_id or 1
        request = struct.pack(
            ">HHHBBHH",
            transaction_id,
            0,
            6,
            self.unit,
            function,
            address,
            1,
        )
        self._writer.write(request)
        await asyncio.wait_for(self._writer.drain(), timeout=3)

        try:
            header = await asyncio.wait_for(self._reader.readexactly(7), timeout=3)
            response_transaction_id, protocol_id, length, response_unit = struct.unpack(
                ">HHHB",
                header,
            )
            if (
                response_transaction_id != transaction_id
                or protocol_id != 0
                or response_unit != self.unit
                or length < 3
            ):
                raise SolarwattProtocolError("Invalid Modbus response header")

            pdu = await asyncio.wait_for(self._reader.readexactly(length - 1), timeout=3)
            response_function = pdu[0]
            if response_function & 0x80:
                code = pdu[1] if len(pdu) > 1 else "<missing>"
                raise SolarwattProtocolError(f"Modbus exception {code}")
            if response_function != function or len(pdu) < 4 or pdu[1] < 2:
                raise SolarwattProtocolError("Invalid Modbus response payload")
        except Exception:
            await self.close()
            raise

        value = struct.unpack(">H", pdu[2:4])[0]
        self._cache[cache_key] = value
        return value


def _decode_modbus_candidate(
    candidate: _ModbusCandidate,
    registers: list[int],
) -> int | float | str | None:
    if not registers:
        return None

    if len(registers) == 1:
        raw = registers[0]
        if candidate.signed and raw >= 0x8000:
            raw -= 0x10000
    elif len(registers) == 2:
        low, high = registers
        raw = (high << 16) | low
        if candidate.signed and raw >= 0x80000000:
            raw -= 0x100000000
    else:
        raw = 0
        for offset, value in enumerate(registers):
            raw |= value << (16 * offset)
        if candidate.signed and raw >= 1 << (len(registers) * 16 - 1):
            raw -= 1 << (len(registers) * 16)

    if candidate.transform is not None:
        value = candidate.transform(raw)
    else:
        value = raw * candidate.scale

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if candidate.min_value is not None and numeric < candidate.min_value:
            return None
        if candidate.max_value is not None and numeric > candidate.max_value:
            return None
        if isinstance(value, float):
            return int(value) if value.is_integer() else round(value, 3)
    return value


def _add_derived_modbus_values(values: dict[str, Any]) -> None:
    if (status := values.get("bms_1_connect_state")) is not None:
        values["bms_1_status"] = "ONLINE" if int(status) > 0 else "OFFLINE"

    fault_values = [
        int(values.get(key) or 0)
        for key in (
            "inverter_fault_1_code",
            "inverter_fault_2_code",
            "inverter_fault_3_code",
        )
    ]
    values["inverter_faults"] = _faults_text(fault_values)


def _faults_text(fault_values: list[int]) -> str:
    active: list[str] = []
    for register_index, value in enumerate(fault_values, start=1):
        if value <= 0:
            continue
        for bit in range(16):
            if value & (1 << bit):
                active.append(f"Register {register_index} bit {bit}")
    return ", ".join(active) if active else "OK"


async def _async_read_modbus_register(
    host: str,
    port: int,
    unit: int,
    function: int,
    address: int,
) -> int:
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=3,
        )
        transaction_id = (address + function) & 0xFFFF
        request = struct.pack(
            ">HHHBBHH",
            transaction_id,
            0,
            6,
            unit,
            function,
            address,
            1,
        )
        writer.write(request)
        await asyncio.wait_for(writer.drain(), timeout=3)

        header = await asyncio.wait_for(reader.readexactly(7), timeout=3)
        response_transaction_id, protocol_id, length, response_unit = struct.unpack(
            ">HHHB",
            header,
        )
        if (
            response_transaction_id != transaction_id
            or protocol_id != 0
            or response_unit != unit
            or length < 3
        ):
            raise SolarwattProtocolError("Invalid Modbus response header")

        pdu = await asyncio.wait_for(reader.readexactly(length - 1), timeout=3)
        response_function = pdu[0]
        if response_function & 0x80:
            code = pdu[1] if len(pdu) > 1 else "<missing>"
            raise SolarwattProtocolError(f"Modbus exception {code}")
        if response_function != function or len(pdu) < 4 or pdu[1] < 2:
            raise SolarwattProtocolError("Invalid Modbus response payload")
        return struct.unpack(">H", pdu[2:4])[0]
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
