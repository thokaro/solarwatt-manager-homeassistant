from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import re
import time
from typing import Any, Optional

import logging

from aiohttp import ClientError, ClientResponseError, CookieJar, ClientSession
from aiohttp.client_exceptions import ContentTypeError
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL


_NUM_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([^\d\s].*)?\s*$")


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


@dataclass
class ParsedState:
    value: Any
    unit: Optional[str] = None
    timestamp_ms: Optional[int] = None


@dataclass
class SOLARWATTItem:
    name: str
    raw: dict[str, Any]
    parsed: ParsedState
    oh_type: str | None
    editable: bool
    label: Optional[str] = None
    category: Optional[str] = None
    group_names: Optional[list[str]] = None


def parse_state(state: Any) -> ParsedState:
    if state is None:
        return ParsedState(value=None)

    s = str(state).strip()

    if s == "NULL":
        return ParsedState(value=None)

    if s in ("ON", "OFF"):
        return ParsedState(value=(s == "ON"))

    # timestamp|value unit
    if "|" in s:
        left, right = s.split("|", 1)
        left = left.strip()
        right = right.strip()
        ts = None
        if left.isdigit():
            try:
                ts = int(left)
            except ValueError:
                ts = None
        ps = parse_state(right)
        ps.timestamp_ms = ts
        return ps

    # numeric + optional unit
    m = _NUM_RE.match(s)
    if m:
        num_s = m.group(1)
        unit = (m.group(2) or "").strip() or None
        try:
            val = float(num_s)

            # ---- Einheiten normalisieren ----
            # SOLARWATT/OpenHAB liefert teils Ws, Wh, kWh, kW, °C, etc.
            if unit:
                unit = unit.replace("\\u00b0", "°")  # falls als Escape reinkommt

            # Ws -> Wh (für HA besser)
            if unit == "Ws":
                val = val / 3600.0
                unit = "Wh"

            # Wh -> kWh (Energy Dashboard & Langzeitwerte)
            # (nur Umrechnung, keine "int"-Abschneidung)
            if unit == "Wh":
                val = val / 1000.0
                unit = "kWh"

            # Rundung je nach Einheit
            if unit == "kWh":
                val = round(val, 3)
            elif unit in ("kW",):
                val = round(val, 3)
            elif unit in ("W", "V", "A", "Hz", "%"):
                # meist ganze Zahlen, aber nicht erzwingen
                val = round(val, 2)
            elif unit in ("°C", "C"):
                unit = "°C"
                val = round(val, 2)

            if isinstance(val, float) and val.is_integer():
                val = int(val)

            return ParsedState(value=val, unit=unit)
        except ValueError:
            pass

    return ParsedState(value=s)


def guess_ha_meta(oh_type: str | None, parsed: ParsedState, item_name: str | None = None) -> dict[str, Any]:
    """Heuristisches Mapping OpenHAB/SOLARWATT -> Home Assistant Sensor-Metadaten.

    Ziel:
    - sinnvolle device_class/state_class
    - HA-konforme Einheiten (native_unit_of_measurement)
    - optional Icons für bessere Übersicht
    """
    unit = parsed.unit if parsed else None
    name_l = (item_name or "").lower()

    # Map string units to HA constants where possible (helps Energy Dashboard & statistics)
    unit_map: dict[str, Any] = {
        "W": UnitOfPower.WATT,
        "kW": UnitOfPower.KILO_WATT,
        "Wh": UnitOfEnergy.WATT_HOUR,
        "kWh": UnitOfEnergy.KILO_WATT_HOUR,
        "V": UnitOfElectricPotential.VOLT,
        "A": UnitOfElectricCurrent.AMPERE,
        "Hz": UnitOfFrequency.HERTZ,
        "°C": UnitOfTemperature.CELSIUS,
        "%": PERCENTAGE,
    }

    meta: dict[str, Any] = {"suggested_unit": unit_map.get(unit, unit)}

    # --- Fallbacks rein aus Einheit/Name ---
    if unit in ("W", "kW"):
        meta.update({"device_class": SensorDeviceClass.POWER, "state_class": SensorStateClass.MEASUREMENT})
    elif unit in ("kWh", "Wh"):
        # Wh is normalized to kWh in parse_state, but keep this safe.
        meta.update({"device_class": SensorDeviceClass.ENERGY, "state_class": SensorStateClass.TOTAL_INCREASING})
    elif unit in ("V",):
        meta.update({"device_class": SensorDeviceClass.VOLTAGE, "state_class": SensorStateClass.MEASUREMENT})
    elif unit in ("A",):
        meta.update({"device_class": SensorDeviceClass.CURRENT, "state_class": SensorStateClass.MEASUREMENT})
    elif unit in ("Hz",):
        meta.update({"device_class": SensorDeviceClass.FREQUENCY, "state_class": SensorStateClass.MEASUREMENT})
    elif unit in ("°C",):
        meta.update({"device_class": SensorDeviceClass.TEMPERATURE, "state_class": SensorStateClass.MEASUREMENT})
    elif unit == "%":
        meta.update({"state_class": SensorStateClass.MEASUREMENT})
        # SOC/Prozentwerte werden oft als Battery angezeigt
        if any(k in name_l for k in ("soc", "stateofcharge", "battery", "akku")):
            meta["device_class"] = SensorDeviceClass.BATTERY

    # Icons (nur Vorschläge)
    if "icon" not in meta:
        if any(k in name_l for k in ("pv", "solar", "generator")):
            meta["icon"] = "mdi:solar-power"
        elif any(k in name_l for k in ("grid", "netz")):
            meta["icon"] = "mdi:transmission-tower"
        elif any(k in name_l for k in ("battery", "akku")):
            meta["icon"] = "mdi:battery"
        elif any(k in name_l for k in ("house", "home", "load", "verbrauch")):
            meta["icon"] = "mdi:home-lightning-bolt"

    # Wenn kein OpenHAB-Typ da ist, bleiben wir bei den Fallbacks.
    if not oh_type:
        return meta

    if oh_type.startswith("Number:Power"):
        meta["device_class"] = SensorDeviceClass.POWER
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfPower.WATT
        return meta

    if oh_type.startswith("Number:Energy"):
        meta["device_class"] = SensorDeviceClass.ENERGY
        meta["state_class"] = SensorStateClass.TOTAL_INCREASING
        if unit is None:
            meta["suggested_unit"] = UnitOfEnergy.KILO_WATT_HOUR
        return meta

    if oh_type.startswith("Number:Temperature"):
        meta["device_class"] = SensorDeviceClass.TEMPERATURE
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfTemperature.CELSIUS
        return meta

    if oh_type.startswith("Number:Frequency"):
        meta["device_class"] = SensorDeviceClass.FREQUENCY
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfFrequency.HERTZ
        return meta

    if oh_type.startswith("Number:ElectricCurrent"):
        meta["device_class"] = SensorDeviceClass.CURRENT
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfElectricCurrent.AMPERE
        return meta

    if oh_type.startswith("Number:ElectricPotential"):
        meta["device_class"] = SensorDeviceClass.VOLTAGE
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfElectricPotential.VOLT
        return meta

    if oh_type.startswith("Number:Dimensionless"):
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit == "%":
            meta["device_class"] = SensorDeviceClass.BATTERY
        return meta

    return meta


class SOLARWATTClient:
    def __init__(self, hass: HomeAssistant, host: str, username: str, password: str):
        # Validate required parameters
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

        self.base = f"http://{host}"
        self.login_url = f"{self.base}/auth/login"
        self.items_url = f"{self.base}/rest/items"
        self.things_url = f"{self.base}/rest/things"

        # Use a dedicated session with CookieJar(unsafe=True) so cookies from IP
        # hosts are accepted. This is REQUIRED for SOLARWATT Manager when accessed
        # by local IP (e.g. 192.168.x.x), because aiohttp's default cookie policy
        # rejects IP-host cookies.
        #
        # We create our own ClientSession here intentionally (instead of HA's
        # shared session) to guarantee the cookie jar behavior.
        self._session = ClientSession(cookie_jar=CookieJar(unsafe=True))
        self._own_session = True

        self.session_ttl = 900
        self._last_login = 0.0
        # Some SOLARWATT versions set the session cookie with a non-IP domain
        # (e.g. "karaf"). In that case aiohttp's cookie jar may not send the
        # cookie back to the manager when we access it by IP. We therefore also
        # store the session cookie value explicitly and attach it to every
        # request.
        self._kiwi_cookie: str | None = None  # e.g. "kiwisessionid=..."
        self._log = logging.getLogger(__name__)

    def _auth_headers(self) -> dict[str, str]:
        """Return headers that ensure SOLARWATT accepts our session."""
        if self._kiwi_cookie:
            return {"Cookie": self._kiwi_cookie}
        return {}

    def _cookie_debug(self) -> str:
        try:
            cookies = self._session.cookie_jar.filter_cookies(self.base)
            # cookies is a SimpleCookie
            names = [m.key for m in cookies.values()]
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

    async def async_close(self) -> None:
        if self._own_session and not self._session.closed:
            await self._session.close()

    async def async_login(self) -> None:
        # SOLARWATT's login form expects classic form fields.
        # Community findings show that adding submit=Login can be required.
        payload = {
            "username": self.username,
            "password": self.password,
            "url": "/",
            "submit": "Login",
        }
        # SOLARWATT responds with "303 See Other" and sets the session cookie
        # (kiwisessionid) in the 303 response. Following redirects can sometimes
        # make cookie handling harder to debug, so we first capture the 303
        # response without redirecting.
        resp_status: int | None = None
        resp_headers: dict[str, str] = {}
        resp_ct: str = ""
        resp_snippet: str = ""

        try:
            async with self._session.post(
                self.login_url,
                data=payload,
                timeout=5,
                allow_redirects=False,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as resp:
                resp_status = resp.status
                resp_headers = dict(resp.headers)
                resp_ct = (resp.headers.get("Content-Type") or "").lower()

                if resp.status not in (200, 303):
                    text = await resp.text()
                    self._log.error(
                        f"Login failed with status {resp.status}. "
                        f"Response: {text[:200]}. Host: {self.host}"
                    )
                    if resp.status in (401, 403):
                        raise SolarwattAuthError(f"Login failed ({resp.status}): {text[:200]}")
                    if resp.status == 404:
                        raise SolarwattNotManagerError(f"Login endpoint not found ({resp.status})")
                    raise SolarwattConnectionError(f"Login failed ({resp.status}): {text[:200]}")

                # Extract kiwisessionid explicitly (works even if cookie domain is odd)
                try:
                    if "kiwisessionid" in resp.cookies:
                        self._kiwi_cookie = f"kiwisessionid={resp.cookies['kiwisessionid'].value}"
                except Exception:
                    # best effort only
                    pass

                # Also look at Set-Cookie header as fallback
                if not self._kiwi_cookie:
                    sc = resp.headers.getall("Set-Cookie", []) if hasattr(resp.headers, "getall") else []
                    for h in sc:
                        if "kiwisessionid=" in h:
                            # take until ';'
                            part = h.split("kiwisessionid=", 1)[1]
                            val = part.split(";", 1)[0]
                            if val:
                                self._kiwi_cookie = f"kiwisessionid={val}"
                                break

                # IMPORTANT: The login response may be HTML (SPA shell) even when
                # login is successful. Treat login as successful **only** if we
                # have a kiwisessionid afterwards.

                # Capture a short snippet for diagnostics (only used on failure).
                if "html" in resp_ct:
                    resp_snippet = await self._read_snippet(resp)

            # If we got redirected, optionally follow once to warm up the session.
            # Not strictly required for /rest/items, but harmless.
            if resp_status == 303:
                loc = resp_headers.get("Location") or resp_headers.get("location")
                if loc:
                    try:
                        async with self._session.get(f"{self.base}{loc}", timeout=5, headers=self._auth_headers()):
                            pass
                    except Exception:
                        # Best effort only; session cookie is what matters.
                        pass

            # Validate: we must have a session cookie now.
            if not self._kiwi_cookie:
                error_msg = (
                    "Login hat keinen kiwisessionid-Cookie geliefert. "
                    f"Status={resp_status}, Content-Type={resp_ct or '<none>'}, "
                    f"Cookies={self._cookie_debug()}, Host={self.host}"
                )
                self._log.error(error_msg)
                raise SolarwattAuthError(error_msg)

            self._last_login = time.time()
            self._log.debug(f"Successfully logged in to {self.host}")
        except Exception as e:
            if isinstance(e, SolarwattError):
                raise
            if isinstance(e, (ClientError, asyncio.TimeoutError)):
                self._log.error(f"Login connection error for {self.host}: {str(e)}")
                raise SolarwattConnectionError(f"Login connection error: {str(e)}") from e
            self._log.error(f"Login error for {self.host}: {str(e)}")
            raise SolarwattConnectionError(f"Login error: {str(e)}") from e

    async def async_probe_manager(self) -> None:
        """Check whether the host looks like a SOLARWATT Manager.

        Raises:
            SolarwattNotManagerError: if /logon.html is missing or unreachable.
            SolarwattConnectionError: on unexpected response codes.
        """
        url = f"{self.base}/logon.html"
        try:
            async with self._session.get(url, timeout=5, allow_redirects=True) as resp:
                if resp.status == 404:
                    raise SolarwattNotManagerError("logon.html not found")
                if 200 <= resp.status < 400:
                    return
                raise SolarwattConnectionError(f"Unexpected probe status: {resp.status}")
        except (ClientError, asyncio.TimeoutError) as e:
            self._log.debug(f"Probe failed for {self.host}: {e}")
            raise SolarwattNotManagerError(f"Probe failed: {e}") from e

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

    async def async_validate_connection(self) -> None:
        """Test connection to SOLARWATT Manager.
        
        Raises:
            SolarwattError: If connection cannot be established or login fails
        """
        try:
            await self.async_login()
            # Try to fetch one item to verify API access
            await self.async_get_items()
        except SolarwattError:
            raise
        except Exception as e:
            raise SolarwattConnectionError(f"Cannot connect to SOLARWATT Manager: {str(e)}") from e

    async def async_get_items(self) -> list[dict[str, Any]]:
        await self._ensure_session()
        try:
            async with self._session.get(self.items_url, timeout=5, headers=self._auth_headers()) as resp:
                # SOLARWATT liefert teils HTML (Login-Seite) statt 401.
                # Dann ist der Status 200, aber Content-Type nicht JSON.
                if resp.status == 401:
                    await self.async_login()
                    async with self._session.get(
                        self.items_url,
                        timeout=5,
                        headers=self._auth_headers(),
                    ) as resp2:
                        resp2.raise_for_status()
                        return await self._ensure_json(resp2, "GET /rest/items (nach 401)")

                resp.raise_for_status()

                ct = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" in ct:
                    # einmal neu einloggen und erneut versuchen
                    await self.async_login()
                    async with self._session.get(
                        self.items_url,
                        timeout=5,
                        headers=self._auth_headers(),
                    ) as resp2:
                        resp2.raise_for_status()
                        return await self._ensure_json(resp2, "GET /rest/items (nach HTML)")
                return await self._ensure_json(resp, "GET /rest/items")
        except ContentTypeError as e:
            # Status ist oft 200 -> deshalb nicht als "HTTP Fehler: 200" maskieren.
            self._log.error(
                f"Content-Type error fetching items from {self.host}: {str(e)}. "
                "Usually indicates HTML login page instead of JSON response."
            )
            raise SolarwattProtocolError(
                "Antwort ist kein JSON (Content-Type stimmt nicht). "
                "SOLARWATT liefert dann meist eine HTML-Loginseite. "
                "Prüfe Host, Port und Login-Daten."
            ) from e
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
        await self._ensure_session()
        try:
            async with self._session.get(self.things_url, timeout=5, headers=self._auth_headers()) as resp:
                if resp.status == 401:
                    await self.async_login()
                    async with self._session.get(
                        self.things_url,
                        timeout=5,
                        headers=self._auth_headers(),
                    ) as resp2:
                        resp2.raise_for_status()
                        return await self._ensure_json(resp2, "GET /rest/things (nach 401)")

                resp.raise_for_status()

                ct = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" in ct:
                    await self.async_login()
                    async with self._session.get(
                        self.things_url,
                        timeout=5,
                        headers=self._auth_headers(),
                    ) as resp2:
                        resp2.raise_for_status()
                        return await self._ensure_json(resp2, "GET /rest/things (nach HTML)")
                return await self._ensure_json(resp, "GET /rest/things")
        except ContentTypeError as e:
            raise SolarwattProtocolError(
                "Antwort für /rest/things ist kein JSON (Content-Type stimmt nicht)."
            ) from e
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

    async def async_get_item(self, item_name: str) -> dict[str, Any]:
        if not item_name or not isinstance(item_name, str):
            raise ValueError("item_name must be a non-empty string")
        await self._ensure_session()
        url = f"{self.items_url}/{item_name}"
        try:
            async with self._session.get(url, timeout=5, headers=self._auth_headers()) as resp:
                if resp.status == 401:
                    await self.async_login()
                    async with self._session.get(url, timeout=5, headers=self._auth_headers()) as resp2:
                        resp2.raise_for_status()
                        return await self._ensure_json(resp2, f"GET /rest/items/{item_name} (nach 401)")
                resp.raise_for_status()
                ct = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" in ct:
                    await self.async_login()
                    async with self._session.get(url, timeout=5, headers=self._auth_headers()) as resp2:
                        resp2.raise_for_status()
                        return await self._ensure_json(resp2, f"GET /rest/items/{item_name} (nach HTML)")

                return await self._ensure_json(resp, f"GET /rest/items/{item_name}")
        except ContentTypeError as e:
            raise SolarwattProtocolError(
                f"Antwort für Item {item_name} ist kein JSON (Content-Type stimmt nicht). Prüfe Proxy/URL/Login."
            ) from e
        except SolarwattError:
            raise
        except ClientResponseError as e:
            if e.status in (401, 403):
                raise SolarwattAuthError(f"HTTP {e.status} for item {item_name}") from e
            if e.status == 404:
                raise SolarwattNotManagerError("Items endpoint not found") from e
            raise SolarwattConnectionError(f"HTTP error {e.status} for item {item_name}") from e
        except (ClientError, asyncio.TimeoutError) as e:
            raise SolarwattConnectionError(f"Connection error for item {item_name}: {e}") from e
        except Exception as e:
            raise SolarwattConnectionError(f"Error for item {item_name}: {e}") from e

class SOLARWATTCoordinator(DataUpdateCoordinator[dict[str, SOLARWATTItem]]):
    def __init__(self, hass: HomeAssistant, entry, client: SOLARWATTClient):
        self.entry = entry
        self.client = client
        self.things: dict[str, dict[str, Any]] = {}

        scan = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        # Validate scan interval: min MIN_SCAN_INTERVAL (5s), max MAX_SCAN_INTERVAL (1h)
        if not isinstance(scan, int) or scan < MIN_SCAN_INTERVAL:
            scan = DEFAULT_SCAN_INTERVAL
        if scan > MAX_SCAN_INTERVAL:
            scan = MAX_SCAN_INTERVAL
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="solarwatt_items",
            update_interval=timedelta(seconds=int(scan)),
        )

    async def _async_update_data(self) -> dict[str, SOLARWATTItem]:
        # Best practice for Home Assistant: do a single poll per update interval and
        # let all entities read from the same snapshot.
        items = await self.client.async_get_items()

        def _to_item(name: str, it: dict[str, Any]) -> SOLARWATTItem:
            return SOLARWATTItem(
                name=name,
                raw=it,
                parsed=parse_state(it.get("state")),
                oh_type=it.get("type"),
                editable=bool(it.get("editable")),
                label=it.get("label"),
                category=it.get("category"),
                group_names=it.get("groupNames"),
            )

        out_all: dict[str, SOLARWATTItem] = {}
        for idx, it in enumerate(items):
            n = it.get("name", f"unknown_{idx}")
            out_all[n] = _to_item(n, it)
        return out_all

    async def async_refresh_things(self) -> None:
        try:
            things = await self.client.async_get_things()
        except SolarwattError as err:
            self.logger.debug("Diagnostics: unable to fetch /rest/things: %s", err)
            return
        except Exception as err:
            self.logger.debug("Diagnostics: unexpected error fetching /rest/things: %s", err, exc_info=True)
            return

        out: dict[str, dict[str, Any]] = {}
        for idx, thing in enumerate(things or []):
            uid = thing.get("UID") or thing.get("uid") or f"unknown_{idx}"
            out[uid] = thing
        self.things = out
        self.async_update_listeners()
