from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from html import unescape
import json
import logging
import re
from secrets import token_urlsafe
from typing import Any
from urllib.parse import quote, urlencode, urljoin

from aiohttp import ClientError, ClientResponseError, ClientSession

KIWIGRID_API_BASE = "https://hems.kiwigrid.com/v11"
KIWIGRID_TOKEN_URL = "https://auth.energymanager.com/auth/realms/solarwatt/protocol/openid-connect/token"
KIWIGRID_CLIENT_ID = "energy-monitor-home"
KIWIGRID_AUTH_URL = "https://auth.energymanager.com/auth/realms/solarwatt/protocol/openid-connect/auth"
KIWIGRID_REDIRECT_URI = "https://new.energymanager.com/rest/auth/auth_grant"
KIWIGRID_CONTEXT_URL = "https://new.energymanager.com/context"

ENDPOINT_BATTERY = "/battery"
ENDPOINT_DEVICE = "/device"
ENDPOINT_DEVICE_OPTIMIZATION = "/device/optimization"
ENDPOINT_ENERGY_FLOW = "/energy-flow"
ENDPOINT_HOME_CONSUMPTION_CONSUMERS = "/home/consumption/consumers"
ENDPOINT_PV_PLANT = "/pv-plant"
ENDPOINT_EVSTATION = "/evstation"
ENDPOINT_PLUG = "/plug"
ENDPOINT_ANALYTICS_CONSUMPTION = "/analytics/consumption"
ENDPOINT_ANALYTICS_PRODUCTION = "/analytics/production"
ENDPOINT_ANALYTICS_STORAGE = "/analytics/storage"
ENDPOINT_ANALYTICS_INDEPENDENCE = "/analytics/independence"
ENDPOINT_ANALYTICS_FINANCE = "/analytics/finance"
ENDPOINT_USER_PROFILE = "/user/profile"

_LOGGER = logging.getLogger(__name__)

ANALYTICS_KIND_CONFIG: dict[str, dict[str, Any]] = {
    "analytics_consumption": {
        "endpoint": ENDPOINT_ANALYTICS_CONSUMPTION,
        "label": "Consumption",
        "today_query": {"type": "POWER"},
        "period_query": {"type": "WORK"},
    },
    "analytics_production": {
        "endpoint": ENDPOINT_ANALYTICS_PRODUCTION,
        "label": "Production",
        "today_query": {"type": "POWER", "isDetailed": "true"},
        "period_query": {"type": "WORK", "isDetailed": "true"},
    },
    "analytics_storage": {
        "endpoint": ENDPOINT_ANALYTICS_STORAGE,
        "label": "Storage",
        "today_query": {"type": "POWER"},
        "period_query": {"type": "WORK"},
    },
    "analytics_independence": {
        "endpoint": ENDPOINT_ANALYTICS_INDEPENDENCE,
        "label": "Independence",
    },
    "analytics_finance": {
        "endpoint": ENDPOINT_ANALYTICS_FINANCE,
        "label": "Finance",
        "uses_currency": True,
    },
}

ANALYTICS_PAYLOAD_PERIODS: tuple[tuple[str, str, str], ...] = (
    ("analytics_consumption", "analytics_consumption", "today"),
    ("analytics_production", "analytics_production", "today"),
    ("analytics_consumption_work_today", "analytics_consumption", "work_today"),
    ("analytics_consumption_month", "analytics_consumption", "month"),
    ("analytics_production_month", "analytics_production", "month"),
    ("analytics_consumption_year", "analytics_consumption", "year"),
    ("analytics_production_year", "analytics_production", "year"),
    ("analytics_storage", "analytics_storage", "today"),
    ("analytics_storage_month", "analytics_storage", "month"),
    ("analytics_storage_year", "analytics_storage", "year"),
    ("analytics_independence", "analytics_independence", "today"),
    ("analytics_independence_month", "analytics_independence", "month"),
    ("analytics_independence_year", "analytics_independence", "year"),
    ("analytics_finance", "analytics_finance", "today"),
    ("analytics_finance_month", "analytics_finance", "month"),
    ("analytics_finance_year", "analytics_finance", "year"),
)


def _analytics_kind_config(kind: str) -> dict[str, Any]:
    config = ANALYTICS_KIND_CONFIG.get(kind)
    if config is None:
        raise KiwiGridHEMSProtocolError(f"Unsupported analytics kind: {kind}")
    return config


def _analytics_where_period(period_id: str) -> str:
    return "work today" if period_id == "work_today" else period_id


def _normalize_access_token(access_token: str) -> str:
    """Normalize a token copied from browser dev tools or curl.

    Users often paste the full Authorization header value ("Bearer ...")
    or a JWT wrapped across multiple lines. The KiwiGrid API expects the raw
    compact JWT in the Authorization header.
    """
    token = str(access_token or "").strip().strip('"').strip("'")
    if token.lower().startswith("bearer "):
        token = token[7:]
    return re.sub(r"\s+", "", token)


class KiwiGridHEMSError(Exception):
    """Base error for KiwiGrid HEMS API failures."""


class KiwiGridHEMSAuthError(KiwiGridHEMSError):
    """Authentication failed or the access token is invalid."""


class KiwiGridHEMSConnectionError(KiwiGridHEMSError):
    """Connection or transport error."""


class KiwiGridHEMSProtocolError(KiwiGridHEMSError):
    """Unexpected API response."""


class KiwiGridHEMSClient:
    """Client for the KiwiGrid HEMS v11 HEMS API.

    The endpoint methods intentionally stay thin. Endpoint specific data
    normalization happens in the mapping functions below, grouped by endpoint.
    """

    def __init__(
        self,
        session: ClientSession,
        access_token: str = "",
        *,
        username: str = "",
        password: str = "",
        api_base: str = KIWIGRID_API_BASE,
    ) -> None:
        self._session = session
        self._access_token = _normalize_access_token(access_token)
        self._refresh_token = ""
        self._username = str(username or "").strip()
        self._password = str(password or "")
        self._api_base = api_base.rstrip("/")

    @property
    def enabled(self) -> bool:
        """Return whether the client can authenticate and make requests."""
        return bool(self._access_token or (self._username and self._password))

    def update_access_token(self, access_token: str) -> None:
        """Update the access token used for subsequent requests."""
        self._access_token = _normalize_access_token(access_token)

    async def async_login(self) -> None:
        """Fetch a HEMS access token using the SOLARWATT OneID web login flow.

        The KiwiGrid HEMS API does not accept a simple resource-owner password
        token for this integration. The web app signs in through SOLARWATT
        OneID, completes /rest/auth/auth_grant on new.energymanager.com and then
        exposes the usable HEMS access token via /context.
        """
        if not self._username or not self._password:
            raise KiwiGridHEMSAuthError("KiwiGrid HEMS username or password is missing")

        context = await self._async_web_login_context()
        oauth = context.get("oauth") if isinstance(context, dict) else None
        oauth = oauth if isinstance(oauth, dict) else {}
        access_token = oauth.get("accessToken") or oauth.get("access_token")
        if not access_token:
            raise KiwiGridHEMSAuthError("HEMS login context did not include an access token")
        self._access_token = _normalize_access_token(str(access_token))

    async def _async_web_login_context(self) -> dict[str, Any]:
        state = token_urlsafe(24)
        nonce = token_urlsafe(24)
        query = urlencode(
            {
                "client_id": KIWIGRID_CLIENT_ID,
                "redirect_uri": KIWIGRID_REDIRECT_URI,
                "response_type": "code",
                "scope": "openid kiwi-cloud-token-claims email profile",
                "state": state,
                "nonce": nonce,
                "kc_idp_hint": "solarwatt-oneid",
            }
        )
        auth_url = f"{KIWIGRID_AUTH_URL}?{query}"

        try:
            async with self._session.get(auth_url, timeout=20, allow_redirects=True) as resp:
                html = await resp.text()
                login_url = str(resp.url)
                if resp.status >= 400:
                    raise KiwiGridHEMSAuthError(
                        f"HEMS login start failed with HTTP {resp.status}"
                    )
        except KiwiGridHEMSError:
            raise
        except ClientError as err:
            raise KiwiGridHEMSConnectionError(f"Connection error during HEMS login start: {err}") from err

        action = self._extract_login_action(html, login_url)
        if not action:
            # If a previous cookie already completed the login, try context directly.
            context = await self._async_fetch_context()
            if context:
                return context
            raise KiwiGridHEMSAuthError("HEMS login page did not contain a login form")

        form_data = {
            "username": self._username,
            "password": self._password,
            "credentialId": "",
            "login": "Anmelden",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            async with self._session.post(
                action,
                data=form_data,
                headers=headers,
                timeout=20,
                allow_redirects=False,
            ) as resp:
                if resp.status in (400, 401, 403):
                    text = await resp.text()
                    raise KiwiGridHEMSAuthError(
                        f"HEMS login credentials rejected: {text[:250]}"
                    )
                next_url = resp.headers.get("Location")
                if not next_url:
                    text = await resp.text()
                    if "login-actions/authenticate" in text or "password" in text.lower():
                        raise KiwiGridHEMSAuthError("HEMS login credentials were not accepted")
                    raise KiwiGridHEMSAuthError("HEMS login did not return a redirect")
                next_url = urljoin(action, next_url)
        except KiwiGridHEMSError:
            raise
        except ClientError as err:
            raise KiwiGridHEMSConnectionError(f"Connection error during HEMS credential submit: {err}") from err

        await self._async_follow_login_redirects(next_url)
        context = await self._async_fetch_context()
        if not context:
            raise KiwiGridHEMSAuthError("HEMS login completed but /context returned no data")
        return context

    async def _async_follow_login_redirects(self, url: str) -> None:
        current = url
        for _ in range(10):
            async with self._session.get(current, timeout=20, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if not location:
                        raise KiwiGridHEMSAuthError("HEMS login redirect without Location header")
                    current = urljoin(str(resp.url), location)
                    continue
                if 200 <= resp.status < 400:
                    return
                text = await resp.text()
                raise KiwiGridHEMSAuthError(
                    f"HEMS login redirect failed with HTTP {resp.status}: {text[:250]}"
                )
        raise KiwiGridHEMSAuthError("HEMS login had too many redirects")

    async def _async_fetch_context(self) -> dict[str, Any]:
        try:
            async with self._session.get(
                KIWIGRID_CONTEXT_URL,
                headers={"Accept": "application/json"},
                timeout=20,
            ) as resp:
                if resp.status in (401, 403):
                    return {}
                resp.raise_for_status()
                text = await resp.text()
                if not text.strip():
                    return {}
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError as err:
                    raise KiwiGridHEMSProtocolError(
                        f"HEMS context response is not JSON: {text[:250]}"
                    ) from err
                return payload if isinstance(payload, dict) else {}
        except KiwiGridHEMSError:
            raise
        except ClientResponseError as err:
            raise KiwiGridHEMSConnectionError(f"HTTP {err.status} while requesting HEMS context") from err
        except ClientError as err:
            raise KiwiGridHEMSConnectionError(f"Connection error while requesting HEMS context: {err}") from err

    @staticmethod
    def _extract_login_action(html: str, base_url: str) -> str | None:
        match = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if not match:
            match = re.search(r'action=["\']([^"\']*login-actions/authenticate[^"\']*)["\']', html, re.IGNORECASE)
        if not match:
            return None
        return urljoin(base_url, unescape(match.group(1)))

    async def async_refresh_token(self) -> None:
        """Refresh the current HEMS access token."""
        if not self._refresh_token:
            await self.async_login()
            return

        data = {
            "grant_type": "refresh_token",
            "client_id": KIWIGRID_CLIENT_ID,
            "refresh_token": self._refresh_token,
        }
        payload = await self._async_post_token(data, where="POST OpenID token refresh")
        self._store_token_payload(payload)

    async def _async_post_token(self, data: dict[str, str], *, where: str) -> dict[str, Any]:
        try:
            async with self._session.post(
                KIWIGRID_TOKEN_URL,
                data=data,
                headers={"Accept": "application/json"},
                timeout=15,
            ) as resp:
                if resp.status in (400, 401, 403):
                    text = await resp.text()
                    raise KiwiGridHEMSAuthError(
                        f"HEMS login failed while requesting {where}: {text[:250]}"
                    )
                resp.raise_for_status()
                try:
                    payload = await resp.json(content_type=None)
                except json.JSONDecodeError as err:
                    raise KiwiGridHEMSProtocolError(
                        f"{where} response is not valid JSON"
                    ) from err
                if not isinstance(payload, dict):
                    raise KiwiGridHEMSProtocolError(f"{where} response is not an object")
                return payload
        except KiwiGridHEMSError:
            raise
        except ClientResponseError as err:
            raise KiwiGridHEMSConnectionError(f"HTTP {err.status} while requesting {where}") from err
        except ClientError as err:
            raise KiwiGridHEMSConnectionError(f"Connection error while requesting {where}: {err}") from err

    def _store_token_payload(self, payload: dict[str, Any]) -> None:
        access_token = payload.get("access_token")
        if not access_token:
            raise KiwiGridHEMSAuthError("HEMS login response did not include an access token")
        self._access_token = _normalize_access_token(str(access_token))
        if refresh_token := payload.get("refresh_token"):
            self._refresh_token = str(refresh_token)

    async def _async_ensure_access_token(self) -> None:
        if self._access_token:
            return
        await self.async_login()

    async def _async_get_json(self, path: str, *, where: str) -> Any:
        await self._async_ensure_access_token()

        for attempt in range(2):
            url = f"{self._api_base}{path}"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Accept": "application/json",
            }

            try:
                async with self._session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status in (401, 403):
                        if attempt == 0 and (self._refresh_token or (self._username and self._password)):
                            await self.async_refresh_token()
                            continue
                        raise KiwiGridHEMSAuthError(
                            f"HEMS authentication failed while requesting {where}"
                        )

                    if resp.status == 404:
                        raise KiwiGridHEMSProtocolError(
                            f"HEMS endpoint not found while requesting {where}"
                        )

                    resp.raise_for_status()
                    content_type = (resp.headers.get("Content-Type") or "").lower()
                    if "json" not in content_type:
                        text = await resp.text()
                        raise KiwiGridHEMSProtocolError(
                            f"HEMS response is not JSON while requesting {where}. "
                            f"Status={resp.status}, Content-Type={content_type or '<none>'}, "
                            f"Snippet={text[:300]}"
                        )
                    try:
                        return await resp.json()
                    except json.JSONDecodeError as err:
                        raise KiwiGridHEMSProtocolError(
                            f"HEMS response is not valid JSON while requesting {where}"
                        ) from err
            except KiwiGridHEMSError:
                raise
            except ClientResponseError as err:
                raise KiwiGridHEMSConnectionError(
                    f"HTTP {err.status} while requesting {where}"
                ) from err
            except ClientError as err:
                raise KiwiGridHEMSConnectionError(
                    f"Connection error while requesting {where}: {err}"
                ) from err

        raise KiwiGridHEMSAuthError(f"HEMS authentication failed while requesting {where}")

    async def _async_send_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any],
        where: str,
    ) -> None:
        await self._async_ensure_access_token()

        for attempt in range(2):
            url = f"{self._api_base}{path}"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            try:
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10,
                ) as resp:
                    if resp.status in (401, 403):
                        if attempt == 0 and (self._refresh_token or (self._username and self._password)):
                            await self.async_refresh_token()
                            continue
                        raise KiwiGridHEMSAuthError(
                            f"HEMS authentication failed while requesting {where}"
                        )

                    if resp.status == 404:
                        raise KiwiGridHEMSProtocolError(
                            f"HEMS endpoint not found while requesting {where}"
                        )

                    resp.raise_for_status()
                    return
            except KiwiGridHEMSError:
                raise
            except ClientResponseError as err:
                raise KiwiGridHEMSConnectionError(
                    f"HTTP {err.status} while requesting {where}"
                ) from err
            except ClientError as err:
                raise KiwiGridHEMSConnectionError(
                    f"Connection error while requesting {where}: {err}"
                ) from err

        raise KiwiGridHEMSAuthError(f"HEMS authentication failed while requesting {where}")

    async def _async_get_list_endpoint(self, path: str, *, where: str) -> list[dict[str, Any]]:
        payload = await self._async_get_json(path, where=where)
        if not isinstance(payload, list):
            raise KiwiGridHEMSProtocolError(f"{where} response is not a list")
        return [item for item in payload if isinstance(item, dict)]

    # /v11/battery ---------------------------------------------------------
    async def async_get_battery(self) -> list[dict[str, Any]]:
        """Fetch battery details from /v11/battery."""
        return await self._async_get_list_endpoint(
            ENDPOINT_BATTERY,
            where="GET /v11/battery",
        )

    # /v11/device ----------------------------------------------------------
    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Fetch device overview from /v11/device."""
        return await self._async_get_list_endpoint(
            ENDPOINT_DEVICE,
            where="GET /v11/device",
        )

    async def async_get_device_optimizations(self) -> list[dict[str, Any]]:
        """Fetch device optimization metadata from /v11/device/optimization."""
        return await self._async_get_list_endpoint(
            ENDPOINT_DEVICE_OPTIMIZATION,
            where="GET /v11/device/optimization",
        )

    # /v11/pv-plant --------------------------------------------------------
    async def async_get_pv_plants(self) -> list[dict[str, Any]]:
        """Fetch PV plant details from /v11/pv-plant."""
        return await self._async_get_list_endpoint(
            ENDPOINT_PV_PLANT,
            where="GET /v11/pv-plant",
        )

    # /v11/evstation -------------------------------------------------------
    async def async_get_evstations(self) -> list[dict[str, Any]]:
        """Fetch EV station details from /v11/evstation."""
        return await self._async_get_list_endpoint(
            ENDPOINT_EVSTATION,
            where="GET /v11/evstation",
        )

    async def async_set_device_optimization_mode(
        self,
        device_id: str,
        optimization_mode: str,
    ) -> None:
        """Set the optimization mode for a KiwiGrid HEMS device."""
        safe_device_id = quote(str(device_id or "").strip(), safe="")
        if not safe_device_id:
            raise KiwiGridHEMSProtocolError("KiwiGrid HEMS device id is missing")
        mode = str(optimization_mode or "").strip().upper()
        if not mode:
            raise KiwiGridHEMSProtocolError("KiwiGrid HEMS optimization mode is missing")

        await self._async_send_json(
            "PATCH",
            f"/device/{safe_device_id}/optimization/config",
            payload={"optimization_mode": mode},
            where="PATCH /v11/device/{id}/optimization/config",
        )

    async def async_set_device_optimization_state(
        self,
        device_id: str,
        target_state: str,
    ) -> None:
        """Switch a KiwiGrid HEMS optimizable device on or off."""
        safe_device_id = quote(str(device_id or "").strip(), safe="")
        if not safe_device_id:
            raise KiwiGridHEMSProtocolError("KiwiGrid HEMS device id is missing")
        state = str(target_state or "").strip().upper()
        if state not in {"ON", "OFF"}:
            raise KiwiGridHEMSProtocolError(
                f"Unsupported KiwiGrid HEMS target state: {target_state}"
            )

        await self._async_send_json(
            "PUT",
            f"/device/{safe_device_id}/optimization/state",
            payload={"target_state": state},
            where="PUT /v11/device/{id}/optimization/state",
        )

    # /v11/plug ------------------------------------------------------------
    async def async_get_plugs(self) -> list[dict[str, Any]]:
        """Fetch smart plug details from /v11/plug."""
        return await self._async_get_list_endpoint(
            ENDPOINT_PLUG,
            where="GET /v11/plug",
        )

    # /v11/energy-flow -----------------------------------------------------
    async def async_get_energy_flow(self) -> dict[str, Any]:
        """Fetch the live energy flow from /v11/energy-flow."""
        payload = await self._async_get_json(
            ENDPOINT_ENERGY_FLOW,
            where="GET /v11/energy-flow",
        )
        if not isinstance(payload, dict):
            raise KiwiGridHEMSProtocolError(
                "GET /v11/energy-flow response is not an object"
            )
        return payload

    async def async_get_home_consumption_consumers(self) -> list[dict[str, Any]]:
        """Fetch live consumer consumption from /v11/home/consumption/consumers."""
        return await self._async_get_list_endpoint(
            ENDPOINT_HOME_CONSUMPTION_CONSUMERS,
            where="GET /v11/home/consumption/consumers",
        )

    # /v11/analytics/consumption ------------------------------------------
    async def async_get_analytics_consumption(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch today's consumption analytics from /v11/analytics/consumption."""
        return await self._async_get_analytics_timeseries(
            "analytics_consumption",
            from_time=from_time,
            to_time=to_time,
        )

    async def async_get_analytics_consumption_year(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch year-to-date work consumption analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_consumption",
            from_time=from_time,
            to_time=to_time,
            period="year",
        )

    async def async_get_analytics_consumption_work_today(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch today's work consumption analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_consumption",
            from_time=from_time,
            to_time=to_time,
            period="today",
            period_id="work_today",
        )

    async def async_get_analytics_consumption_month(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch month-to-date work consumption analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_consumption",
            from_time=from_time,
            to_time=to_time,
            period="month",
        )

    # /v11/analytics/production -------------------------------------------
    async def async_get_analytics_production(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch today's production analytics from /v11/analytics/production."""
        return await self._async_get_analytics_timeseries(
            "analytics_production",
            from_time=from_time,
            to_time=to_time,
        )

    async def async_get_analytics_production_year(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch year-to-date work production analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_production",
            from_time=from_time,
            to_time=to_time,
            period="year",
        )

    async def async_get_analytics_production_month(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch month-to-date work production analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_production",
            from_time=from_time,
            to_time=to_time,
            period="month",
        )

    # /v11/analytics/storage ----------------------------------------------
    async def async_get_analytics_storage(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch today's storage analytics from /v11/analytics/storage."""
        return await self._async_get_analytics_timeseries(
            "analytics_storage",
            from_time=from_time,
            to_time=to_time,
        )

    async def async_get_analytics_storage_year(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch year-to-date work storage analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_storage",
            from_time=from_time,
            to_time=to_time,
            period="year",
        )

    async def async_get_analytics_storage_month(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch month-to-date work storage analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_storage",
            from_time=from_time,
            to_time=to_time,
            period="month",
        )

    # /v11/analytics/independence -----------------------------------------
    async def async_get_analytics_independence(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch today's independence analytics from /v11/analytics/independence."""
        return await self._async_get_analytics_timeseries(
            "analytics_independence",
            from_time=from_time,
            to_time=to_time,
        )

    async def async_get_analytics_independence_year(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch year-to-date independence analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_independence",
            from_time=from_time,
            to_time=to_time,
            period="year",
        )

    async def async_get_analytics_independence_month(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch month-to-date independence analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_independence",
            from_time=from_time,
            to_time=to_time,
            period="month",
        )

    # /v11/analytics/finance ----------------------------------------------
    async def async_get_analytics_finance(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch today's finance analytics from /v11/analytics/finance."""
        return await self._async_get_analytics_timeseries(
            "analytics_finance",
            from_time=from_time,
            to_time=to_time,
        )

    async def async_get_analytics_finance_year(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch year-to-date finance analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_finance",
            from_time=from_time,
            to_time=to_time,
            period="year",
        )

    async def async_get_analytics_finance_month(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch month-to-date finance analytics."""
        return await self._async_get_analytics_timeseries(
            "analytics_finance",
            from_time=from_time,
            to_time=to_time,
            period="month",
        )

    async def async_get_user_profile(self) -> dict[str, Any]:
        """Fetch user profile preferences from /v11/user/profile."""
        payload = await self._async_get_json(
            ENDPOINT_USER_PROFILE,
            where="GET /v11/user/profile",
        )
        if not isinstance(payload, dict):
            raise KiwiGridHEMSProtocolError(
                "GET /v11/user/profile response is not an object"
            )
        return payload

    async def _async_get_analytics_timeseries(
        self,
        kind: str,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        period: str = "today",
        period_id: str | None = None,
    ) -> dict[str, Any]:
        config = _analytics_kind_config(kind)
        endpoint = str(config["endpoint"])
        normalized_period_id = period_id or period
        if normalized_period_id == "today":
            start, end = _daily_analytics_time_window(
                from_time=from_time,
                to_time=to_time,
            )
            query_values = dict(config.get("today_query", {}))
            where_period = ""
        else:
            start, end = _work_summary_time_window(
                period=period,
                from_time=from_time,
                to_time=to_time,
            )
            query_values = dict(config.get("period_query", {}))
            where_period = f" {_analytics_where_period(normalized_period_id)}"
        query_values = {
            "from": _format_analytics_time(start),
            "to": _format_analytics_time(end),
            **query_values,
        }
        where = f"GET /v11{endpoint}{where_period}"
        payload = await self._async_get_json(
            f"{endpoint}?{urlencode(query_values)}",
            where=where,
        )
        if not isinstance(payload, dict):
            raise KiwiGridHEMSProtocolError(f"{where} response is not an object")
        return payload


# Endpoint payload mapping -------------------------------------------------


def hems_payloads_to_items(
    *,
    batteries: list[dict[str, Any]] | None = None,
    devices: list[dict[str, Any]] | None = None,
    device_optimizations: list[dict[str, Any]] | None = None,
    pv_plants: list[dict[str, Any]] | None = None,
    evstations: list[dict[str, Any]] | None = None,
    plugs: list[dict[str, Any]] | None = None,
    energy_flow: dict[str, Any] | None = None,
    home_consumption_consumers: list[dict[str, Any]] | None = None,
    analytics_consumption: dict[str, Any] | None = None,
    analytics_production: dict[str, Any] | None = None,
    analytics_consumption_work_today: dict[str, Any] | None = None,
    analytics_consumption_month: dict[str, Any] | None = None,
    analytics_production_month: dict[str, Any] | None = None,
    analytics_consumption_year: dict[str, Any] | None = None,
    analytics_production_year: dict[str, Any] | None = None,
    analytics_storage: dict[str, Any] | None = None,
    analytics_storage_month: dict[str, Any] | None = None,
    analytics_storage_year: dict[str, Any] | None = None,
    analytics_independence: dict[str, Any] | None = None,
    analytics_independence_month: dict[str, Any] | None = None,
    analytics_independence_year: dict[str, Any] | None = None,
    analytics_finance: dict[str, Any] | None = None,
    analytics_finance_month: dict[str, Any] | None = None,
    analytics_finance_year: dict[str, Any] | None = None,
    user_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert KiwiGrid HEMS payloads to OpenHAB-like item records.

    Mapping is intentionally grouped by endpoint so adding further endpoints
    such as analytics or optimization later does not affect existing mappings.
    """
    specific_ids = _known_specific_device_ids(
        batteries=batteries,
        pv_plants=pv_plants,
        evstations=evstations,
        plugs=plugs,
    )
    device_names_by_id = _device_names_by_id(
        batteries=batteries,
        devices=devices,
        device_optimizations=device_optimizations,
        pv_plants=pv_plants,
        evstations=evstations,
        plugs=plugs,
    )
    optimization_by_id = _payloads_by_id(device_optimizations or [])
    batteries = _merge_optimization_payloads(batteries or [], optimization_by_id)
    devices = _merge_optimization_payloads(devices or [], optimization_by_id)
    evstations = _merge_optimization_payloads(evstations or [], optimization_by_id)
    plugs = _merge_optimization_payloads(plugs or [], optimization_by_id)

    items: list[dict[str, Any]] = []
    items.extend(battery_endpoint_to_items(batteries))
    items.extend(pv_plant_endpoint_to_items(pv_plants or []))
    items.extend(evstation_endpoint_to_items(evstations))
    items.extend(plug_endpoint_to_items(plugs))
    items.extend(device_endpoint_to_items(devices, skip_ids=specific_ids))
    items.extend(
        energy_flow_endpoint_to_items(
            energy_flow or {},
            device_names_by_id=device_names_by_id,
        )
    )
    items.extend(consumers_endpoint_to_items(home_consumption_consumers or []))
    analytics_payloads = {
        "analytics_consumption": analytics_consumption,
        "analytics_production": analytics_production,
        "analytics_consumption_work_today": analytics_consumption_work_today,
        "analytics_consumption_month": analytics_consumption_month,
        "analytics_production_month": analytics_production_month,
        "analytics_consumption_year": analytics_consumption_year,
        "analytics_production_year": analytics_production_year,
        "analytics_storage": analytics_storage,
        "analytics_storage_month": analytics_storage_month,
        "analytics_storage_year": analytics_storage_year,
        "analytics_independence": analytics_independence,
        "analytics_independence_month": analytics_independence_month,
        "analytics_independence_year": analytics_independence_year,
        "analytics_finance": analytics_finance,
        "analytics_finance_month": analytics_finance_month,
        "analytics_finance_year": analytics_finance_year,
    }
    for payload_key, kind, period_id in ANALYTICS_PAYLOAD_PERIODS:
        if payload := analytics_payloads.get(payload_key):
            items.extend(
                _analytics_payload_to_items(
                    kind,
                    payload,
                    period_id=period_id,
                    user_profile=user_profile or {},
                )
        )
    return [item for item in items if item is not None]


# /v11/battery -------------------------------------------------------------


def battery_endpoint_to_items(payload: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map /v11/battery payloads to items."""
    items: list[dict[str, Any]] = []
    for battery in payload:
        prefix = _hems_prefix("battery", battery)
        items.extend(
            _hems_common_device_items(prefix, battery)
            + [
                _number_item(prefix, "state_of_charge", battery.get("state_of_charge"), "%", "Number:Dimensionless", scale=100),
                _number_item(prefix, "state_of_charge_minimum", battery.get("state_of_charge_minimum"), "%", "Number:Dimensionless", scale=100),
                _number_item(prefix, "backup_state_of_charge", battery.get("backup_state_of_charge"), "%", "Number:Dimensionless", scale=100),
                _number_item(prefix, "work_capacity", battery.get("work_capacity"), "Wh", "Number:Energy"),
                _number_item(prefix, "power_ac_in_max", battery.get("power_ac_in_max"), "W", "Number:Power"),
                _number_item(prefix, "power_ac_out_max", battery.get("power_ac_out_max"), "W", "Number:Power"),
                _string_item(prefix, "mode", battery.get("mode")),
                _bool_item(prefix, "backup_active", battery.get("backup_active")),
                _bool_item(prefix, "backup_available", battery.get("backup_available")),
                _bool_item(prefix, "time_of_use_available", battery.get("time_of_use_available")),
            ]
        )
    return items


# /v11/pv-plant ------------------------------------------------------------


def pv_plant_endpoint_to_items(payload: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map /v11/pv-plant payloads to items."""
    items: list[dict[str, Any]] = []
    for pv_plant in payload:
        prefix = _hems_prefix("pv_plant", pv_plant)
        items.extend(
            _hems_common_device_items(prefix, pv_plant)
            + [
                _number_item(prefix, "power_installed_peak", pv_plant.get("power_installed_peak"), "W", "Number:Power"),
                _number_item(prefix, "module_orientation", _value_from_unit_dict(pv_plant.get("module_orientation")), "°", "Number"),
                _number_item(prefix, "module_tilt", _value_from_unit_dict(pv_plant.get("module_tilt")), "°", "Number"),
                _string_item(prefix, "date_installation", _date_ms_to_iso(pv_plant.get("date_installation"))),
            ]
        )
    return items


# /v11/evstation -----------------------------------------------------------


def evstation_endpoint_to_items(payload: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map /v11/evstation payloads to items."""
    items: list[dict[str, Any]] = []
    for evstation in payload:
        prefix = _hems_prefix("evstation", evstation)
        items.extend(
            _hems_common_device_items(prefix, evstation)
            + [
                _string_item(prefix, "mode", evstation.get("mode")),
                _string_item(prefix, "connectivity_status", evstation.get("connectivity_status")),
            ]
        )
    return items


# /v11/plug ----------------------------------------------------------------


def plug_endpoint_to_items(payload: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map /v11/plug payloads to items."""
    items: list[dict[str, Any]] = []
    for plug in payload:
        prefix = _hems_prefix("plug", plug)
        items.extend(_hems_common_device_items(prefix, plug))
    return items


# /v11/energy-flow ---------------------------------------------------------


def energy_flow_endpoint_to_items(
    payload: dict[str, Any],
    *,
    device_names_by_id: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Map /v11/energy-flow payloads to dedicated KiwiGrid Flow items."""
    if not isinstance(payload, Mapping):
        return []

    items: list[dict[str, Any] | None] = [
        _kiwigrid_flow_power_item("consumption_in", _nested_number(payload, "consumption", "in")),
        _kiwigrid_flow_power_item(
            "consumption_direct_consumption",
            _nested_number(payload, "consumption", "direct_consumption"),
        ),
        _kiwigrid_flow_power_item("grid_in", _nested_number(payload, "grid", "in")),
        _kiwigrid_flow_power_item("grid_out", _nested_number(payload, "grid", "out")),
        _kiwigrid_flow_power_item("grid_balance", _nested_number(payload, "grid", "balance")),
        _kiwigrid_flow_power_item("pv_out", _nested_number(payload, "pv", "out")),
        _kiwigrid_flow_power_item("battery_in", _nested_number(payload, "battery", "in")),
        _kiwigrid_flow_power_item("battery_out", _nested_number(payload, "battery", "out")),
        _kiwigrid_flow_power_item(
            "battery_in_from_grid",
            _nested_number(payload, "battery", "in_from_grid"),
        ),
        _kiwigrid_flow_power_item(
            "battery_out_to_grid",
            _nested_number(payload, "battery", "out_to_grid"),
        ),
        _kiwigrid_flow_percentage_item("battery_soc", _nested_number(payload, "battery", "soc")),
        _kiwigrid_flow_power_item(
            "battery_balance",
            _nested_number(payload, "battery", "balance"),
        ),
        _kiwigrid_flow_power_item("ev_in", _nested_number(payload, "ev", "in")),
        _kiwigrid_flow_power_item("ev_out", _nested_number(payload, "ev", "out")),
        _kiwigrid_flow_power_item("ev_balance", _nested_number(payload, "ev", "balance")),
        _kiwigrid_flow_bool_item("ev_bidirectional", _nested_value(payload, "ev", "bidirectional")),
    ]

    for section in ("consumption", "grid", "pv", "battery", "ev"):
        section_payload = payload.get(section)
        if not isinstance(section_payload, Mapping):
            continue
        devices = section_payload.get("devices")
        if not isinstance(devices, list):
            continue
        for device in devices:
            if not isinstance(device, Mapping):
                continue
            device_id = str(device.get("id") or "").strip()
            device_key = _flow_device_key(device_id, device_names_by_id or {})
            if not device_key:
                continue
            for key, value in device.items():
                if key == "id":
                    continue
                suffix = f"{device_key}_{_slug(str(key))}"
                if key == "soc":
                    items.append(_kiwigrid_flow_percentage_item(suffix, value))
                elif isinstance(value, bool):
                    items.append(_kiwigrid_flow_bool_item(suffix, value))
                else:
                    items.append(_kiwigrid_flow_power_item(suffix, value))

    return [item for item in items if item is not None]


def consumers_endpoint_to_items(payload: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map /v11/home/consumption/consumers payloads to KiwiGrid Flow items."""
    items: list[dict[str, Any] | None] = []
    for consumer in payload:
        if not isinstance(consumer, Mapping):
            continue
        name = str(consumer.get("name") or "").strip()
        consumer_id = str(consumer.get("id") or "").strip()
        consumer_key = _slug(name or consumer_id)
        if not consumer_key:
            continue
        items.append(
            _kiwigrid_flow_power_item(
                f"{consumer_key}_consumption",
                consumer.get("consumption"),
            )
        )
    return [item for item in items if item is not None]


def _energy_overview_power_item(name: str, value: Any) -> dict[str, Any]:
    return {
        "name": name,
        "label": name,
        "state": _formatted_number_state(value, "W", decimals=3),
        "type": "Number:Power",
        "editable": False,
        "category": "energy_overview",
        "stateDescription": {"pattern": "%.0f W"},
    }


def _energy_overview_percentage_item(name: str, value: Any) -> dict[str, Any]:
    return {
        "name": name,
        "label": name,
        "state": _formatted_number_state(value, "%", decimals=1),
        "type": "Number:Dimensionless",
        "editable": False,
        "category": "energy_overview",
        "stateDescription": {"pattern": "%.1f %%"},
    }


def _kiwigrid_flow_power_item(name: str, value: Any) -> dict[str, Any]:
    item = _energy_overview_power_item(name, value)
    item["name"] = f"hems_flow_{name}"
    item["label"] = name.replace("_", " ").title()
    item["category"] = "kiwigrid_flow"
    return item


def _kiwigrid_flow_percentage_item(name: str, value: Any) -> dict[str, Any]:
    numeric_value = (
        value * 100
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else value
    )
    item = _energy_overview_percentage_item(name, numeric_value)
    item["name"] = f"hems_flow_{name}"
    item["label"] = name.replace("_", " ").title()
    item["category"] = "kiwigrid_flow"
    return item


def _kiwigrid_flow_bool_item(name: str, value: Any) -> dict[str, Any] | None:
    item = _bool_item("hems_flow", name, value)
    if item is not None:
        item["category"] = "kiwigrid_flow"
    return item


def _flow_device_key(device_id: str, device_names_by_id: Mapping[str, str]) -> str | None:
    """Return a stable flow device key using the HEMS device name when known."""
    device_name = str(device_names_by_id.get(device_id) or "").strip()
    return _slug(device_name) if device_name else None


def _formatted_number_state(value: Any, unit: str, *, decimals: int) -> str:
    if isinstance(value, bool) or value is None:
        return "NULL"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "NULL"
    suffix = f" {unit}" if unit else ""
    if numeric.is_integer():
        return f"{int(numeric)}{suffix}"
    return f"{numeric:.{decimals}f}".rstrip("0").rstrip(".") + suffix


# /v11/device --------------------------------------------------------------


def device_endpoint_to_items(
    payload: Iterable[dict[str, Any]],
    *,
    skip_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Map /v11/device payloads to items.

    Devices that are already represented by endpoint-specific payloads are
    skipped to avoid duplicate entities for the same physical device.
    """
    skipped = skip_ids or set()
    items: list[dict[str, Any]] = []
    for device in payload:
        if _payload_id(device) in skipped:
            continue
        prefix = _hems_prefix("device", device)
        items.extend(_hems_common_device_items(prefix, device))
        if "mode" in device:
            items.append(_string_item(prefix, "mode", device.get("mode")))
    return items


# /v11/analytics and forecast time series ---------------------------------


def _analytics_payload_to_items(
    kind: str,
    payload: dict[str, Any],
    *,
    period_id: str = "today",
    user_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Map one configured analytics payload to synthetic HEMS items."""
    config = _analytics_kind_config(kind)
    period_prefix = "today" if period_id == "work_today" else period_id
    return _analytics_timeseries_endpoint_to_items(
        payload,
        kind=kind,
        category_label=str(config["label"]),
        property_prefix=str(config.get("property_prefix") or ""),
        period_id=period_id,
        period_prefix=period_prefix,
        include_latest=period_id == "today",
        currency=_profile_currency(user_profile)
        if config.get("uses_currency")
        else "",
    )


def _analytics_timeseries_endpoint_to_items(
    payload: dict[str, Any],
    *,
    kind: str,
    category_label: str,
    property_prefix: str = "",
    period_id: str = "today",
    period_prefix: str = "today",
    include_latest: bool = True,
    skip_series_names: set[str] | None = None,
    currency: str = "",
) -> list[dict[str, Any]]:
    """Map a KiwiGrid analytics timeseries payload to compact daily sensors."""
    timeseries = payload.get("timeseries")
    if not isinstance(timeseries, list) or not timeseries:
        return []

    prefix = _analytics_item_prefix(kind)
    items: list[dict[str, Any]] = []
    skipped = {str(name).strip().lower() for name in skip_series_names or set()}
    device_lookup = _analytics_devices_by_id(payload.get("devices"))
    include_device_names = len(device_lookup) > 1
    for series in timeseries:
        if not isinstance(series, dict):
            continue
        series_display = str(series.get("name") or series.get("id") or "unknown")
        if series_display.strip().lower() in skipped:
            continue
        series_slug = _slug(series_display)
        device = device_lookup.get(str(series.get("guid") or "").strip())
        if (
            include_device_names
            and device is not None
            and kind in {"analytics_consumption", "analytics_production"}
        ):
            suffix = _analytics_device_item_suffix(
                period_prefix,
                category_label,
                str(device.get("name") or device.get("id") or ""),
                series_slug,
            )
            label = _analytics_device_item_label(
                period_prefix,
                category_label,
                str(device.get("name") or device.get("id") or ""),
                series_display,
            )
        else:
            suffix = _analytics_item_suffix(
                period_prefix,
                category_label,
                series_slug,
                property_prefix=property_prefix,
            )
            label = _analytics_item_label(
                period_prefix,
                category_label,
                series_display,
                property_prefix=property_prefix,
            )
        aggregated_unit, aggregated_type, aggregated_scale = _analytics_unit_type_scale(
            series.get("unit"),
            aggregated=True,
            currency=currency,
        )
        items.append(
            _number_item(
                prefix,
                suffix,
                series.get("aggregated"),
                aggregated_unit,
                aggregated_type,
                scale=aggregated_scale,
                label=label,
            )
        )
        latest = _latest_timeseries_value(series.get("values"))
        if include_latest and latest is not None:
            _, latest_value = latest
            unit, item_type, latest_scale = _analytics_unit_type_scale(
                series.get("unit"),
                aggregated=False,
                currency=currency,
            )
            items.append(
                _number_item(
                    prefix,
                    f"{suffix}_latest",
                    latest_value,
                    unit,
                    item_type,
                    scale=latest_scale,
                    label=f"{label} Latest",
                )
            )

    return items


def _analytics_item_prefix(kind: str) -> str:
    """Return the synthetic analytics item prefix without a technical id."""
    return f"hems_{kind}"


def _analytics_item_suffix(
    period_prefix: str,
    category_label: str,
    series_slug: str,
    *,
    property_prefix: str = "",
) -> str:
    category_slug = _slug(category_label)
    return "_".join(
        part
        for part in (
            period_prefix,
            category_slug,
            property_prefix,
            series_slug,
        )
        if part
    )


def _analytics_item_label(
    period_prefix: str,
    category_label: str,
    series_display: str,
    *,
    property_prefix: str = "",
) -> str:
    words = [_analytics_period_label(period_prefix), category_label]
    if property_prefix:
        words.append(property_prefix.replace("_", " ").title().replace(" ", ""))
    words.append(series_display)
    return " ".join(word for word in words if word)


def _analytics_device_item_label(
    period_prefix: str,
    category_label: str,
    device_name: str,
    series_display: str,
) -> str:
    return " ".join(
        word
        for word in (
            _analytics_period_label(period_prefix),
            category_label,
            device_name,
            series_display,
        )
        if word
    )


def _analytics_device_item_suffix(
    period_prefix: str,
    category_label: str,
    device_name: str,
    series_slug: str,
) -> str:
    return "_".join(
        part
        for part in (
            period_prefix,
            _slug(category_label),
            _slug(device_name),
            series_slug,
        )
        if part
    )


def _analytics_period_label(period_prefix: str) -> str:
    return {
        "today": "Today",
        "month": "Month",
        "year": "Year",
    }.get(period_prefix, period_prefix.replace("_", " ").title())


def _analytics_devices_by_id(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        return {}
    devices: dict[str, Mapping[str, Any]] = {}
    for device in value:
        if not isinstance(device, Mapping):
            continue
        device_id = str(device.get("id") or "").strip()
        if device_id:
            devices[device_id] = device
    return devices


def _generic_value_item(prefix: str, suffix: str, value: Any) -> dict[str, Any] | None:
    if isinstance(value, bool):
        return _bool_item(prefix, suffix, value)
    if isinstance(value, (int, float)):
        return _number_item(prefix, suffix, value, "", "Number")
    return _string_item(prefix, suffix, value)


# HEMS device/thing mapping -------------------------------------------------


def hems_payloads_to_things(
    *,
    batteries: list[dict[str, Any]] | None = None,
    devices: list[dict[str, Any]] | None = None,
    device_optimizations: list[dict[str, Any]] | None = None,
    pv_plants: list[dict[str, Any]] | None = None,
    evstations: list[dict[str, Any]] | None = None,
    plugs: list[dict[str, Any]] | None = None,
    energy_flow: dict[str, Any] | None = None,
    home_consumption_consumers: list[dict[str, Any]] | None = None,
    analytics_consumption: dict[str, Any] | None = None,
    analytics_production: dict[str, Any] | None = None,
    analytics_consumption_work_today: dict[str, Any] | None = None,
    analytics_consumption_month: dict[str, Any] | None = None,
    analytics_production_month: dict[str, Any] | None = None,
    analytics_consumption_year: dict[str, Any] | None = None,
    analytics_production_year: dict[str, Any] | None = None,
    analytics_storage: dict[str, Any] | None = None,
    analytics_storage_month: dict[str, Any] | None = None,
    analytics_storage_year: dict[str, Any] | None = None,
    analytics_independence: dict[str, Any] | None = None,
    analytics_independence_month: dict[str, Any] | None = None,
    analytics_independence_year: dict[str, Any] | None = None,
    analytics_finance: dict[str, Any] | None = None,
    analytics_finance_month: dict[str, Any] | None = None,
    analytics_finance_year: dict[str, Any] | None = None,
    user_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert KiwiGrid HEMS payloads to OpenHAB-like thing records.

    Each endpoint-specific payload becomes its own Home Assistant device via
    the existing thing/device mapping. This keeps HEMS battery, PV plant, EV
    station, plug and generic device data visually separated in Home Assistant.
    """
    specific_ids = _known_specific_device_ids(
        batteries=batteries,
        pv_plants=pv_plants,
        evstations=evstations,
        plugs=plugs,
    )
    optimization_by_id = _payloads_by_id(device_optimizations or [])
    batteries = _merge_optimization_payloads(batteries or [], optimization_by_id)
    devices = _merge_optimization_payloads(devices or [], optimization_by_id)
    evstations = _merge_optimization_payloads(evstations or [], optimization_by_id)
    plugs = _merge_optimization_payloads(plugs or [], optimization_by_id)

    things: list[dict[str, Any]] = []
    things.extend(_endpoint_payloads_to_things("battery", batteries))
    things.extend(_endpoint_payloads_to_things("pv_plant", pv_plants or []))
    things.extend(_endpoint_payloads_to_things("evstation", evstations))
    things.extend(_endpoint_payloads_to_things("plug", plugs))
    things.extend(
        _endpoint_payloads_to_things(
            "device",
            (device for device in devices if _payload_id(device) not in specific_ids),
        )
    )
    analytics_payloads = {
        "analytics_consumption": analytics_consumption,
        "analytics_production": analytics_production,
        "analytics_consumption_work_today": analytics_consumption_work_today,
        "analytics_consumption_month": analytics_consumption_month,
        "analytics_production_month": analytics_production_month,
        "analytics_consumption_year": analytics_consumption_year,
        "analytics_production_year": analytics_production_year,
        "analytics_storage": analytics_storage,
        "analytics_storage_month": analytics_storage_month,
        "analytics_storage_year": analytics_storage_year,
        "analytics_independence": analytics_independence,
        "analytics_independence_month": analytics_independence_month,
        "analytics_independence_year": analytics_independence_year,
        "analytics_finance": analytics_finance,
        "analytics_finance_month": analytics_finance_month,
        "analytics_finance_year": analytics_finance_year,
    }
    for payload_key, kind, period_id in ANALYTICS_PAYLOAD_PERIODS:
        if payload := analytics_payloads.get(payload_key):
            profile = user_profile if _analytics_kind_config(kind).get("uses_currency") else None
            things.extend(
                _endpoint_payloads_to_things(
                    kind,
                    [
                        _analytics_payload(
                            kind,
                            payload,
                            period_id=period_id,
                            user_profile=profile,
                        )
                    ],
                )
            )
    return things


def _endpoint_payloads_to_things(
    kind: str,
    payloads: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    things: list[dict[str, Any]] = []
    for payload in payloads:
        thing = _hems_payload_to_thing(kind, payload)
        if thing is not None:
            things.append(thing)
    return things


def _hems_payload_to_thing(kind: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    is_synthetic_hems_device = _is_synthetic_hems_kind(kind)
    prefix = (
        _analytics_item_prefix(kind)
        if is_synthetic_hems_device and kind.startswith("analytics_")
        else _hems_prefix(kind, payload)
    )
    # Synthetic analytics/home endpoints are one selectable HEMS device.
    # The period remains in item names as today/year, not in the device UID.
    raw_uid = (
        "kiwigrid-hems"
        if is_synthetic_hems_device
        else _payload_id(payload) or str(payload.get("serial_number") or "unknown").strip()
    )
    uid = raw_uid or f"kiwigrid-hems:{kind}:unknown"
    title = _hems_kind_title(kind)
    label = str(payload.get("name") or title).strip() or title
    items = _items_for_hems_payload(kind, payload)
    if not items:
        return None

    channels = []
    for item in items:
        if not item:
            continue
        item_name = str(item.get("name") or "").strip()
        if not item_name:
            continue
        suffix = item_name.removeprefix(f"{prefix}_")
        # Prefix HEMS channels to avoid channel UID collisions when HEMS
        # payloads are merged into an existing local HEMS thing with the same
        # device UUID.
        channel_id = f"hems_{kind}_{_slug(suffix)}"
        channels.append(
            {
                "id": channel_id,
                "uid": f"{uid}:{channel_id}",
                "label": item.get("label") or suffix.replace("_", " ").title(),
                "itemType": item.get("type") or "String",
                "linkedItems": [item_name],
                "properties": {
                    "kiwigrid.endpoint": _hems_kind_endpoint(kind),
                    "kiwigrid.kind": kind,
                    "kig.meta.scope": "kiwigrid_hems",
                },
            }
        )

    return {
        "UID": uid,
        "uid": uid,
        "label": label,
        "thingTypeUID": f"kiwigrid-hems:{kind}",
        "thingTypeUid": f"kiwigrid-hems:{kind}",
        "statusInfo": {
            "status": _hems_device_status(payload),
            "statusDetail": "NONE",
        },
        "properties": _hems_thing_properties(kind, payload, title),
        "channels": channels,
    }


def _items_for_hems_payload(kind: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if kind == "battery":
        return battery_endpoint_to_items([payload])
    if kind == "pv_plant":
        return pv_plant_endpoint_to_items([payload])
    if kind == "evstation":
        return evstation_endpoint_to_items([payload])
    if kind == "plug":
        return plug_endpoint_to_items([payload])
    if kind == "device":
        return device_endpoint_to_items([payload])
    if kind in ANALYTICS_KIND_CONFIG:
        period_id = str(payload.get("id") or "").strip().lower()
        profile = payload.get("user_profile") if isinstance(payload, Mapping) else None
        return _analytics_payload_to_items(
            kind,
            payload,
            period_id=period_id or "today",
            user_profile=profile if isinstance(profile, dict) else None,
        )
    return []


def _hems_thing_properties(kind: str, payload: dict[str, Any], title: str) -> dict[str, str]:
    model = _hems_device_model(payload, title)
    is_synthetic_hems_device = _is_synthetic_hems_kind(kind)
    generated_label = "KiwiGrid HEMS v11" if is_synthetic_hems_device else str(model or title).strip()
    props: dict[str, str] = {
        "thingTypeTitle": title,
        "thingTypeCategory": "KIWIGRID_HEMS",
        "kiwigridEndpoint": _hems_kind_endpoint(kind),
        "kiwigridKind": kind,
        # Home Assistant's device metadata builder uses generatedLabel as
        # compact model/detail text. Keep the endpoint device name in
        # thing["label"], and store the model/detail here.
        "generatedLabel": generated_label,
    }
    for key, value in (
        ("vendor", payload.get("manufacturer")),
        ("manufacturer", payload.get("manufacturer")),
        ("serialNumber", payload.get("serial_number")),
        ("firmware", payload.get("firmware")),
        ("model", generated_label if is_synthetic_hems_device else model),
        ("identifier", None if is_synthetic_hems_device else payload.get("id") or payload.get("uuid")),
    ):
        if text := str(value or "").strip():
            props[key] = text
    props.update(_hems_optimization_properties(payload))
    return props


def _is_synthetic_hems_kind(kind: str) -> bool:
    """Return True for HEMS endpoints grouped under the synthetic HEMS device."""
    return kind.startswith(("analytics_", "forecast_"))


def _hems_device_model(payload: Mapping[str, Any], title: str) -> str:
    """Return a useful model/detail string for Home Assistant device metadata."""
    for value in (payload.get("model_code"), payload.get("type"), title):
        text = str(value or "").strip()
        if text and not text.isdigit():
            return text
    return str(title or "").strip()


def _hems_optimization_properties(payload: dict[str, Any]) -> dict[str, str]:
    optimization = payload.get("optimization")
    if not isinstance(optimization, dict):
        return {}

    config = optimization.get("config")
    config = config if isinstance(config, dict) else {}
    props: dict[str, str] = {}
    for key, value in (
        ("optimizationMode", config.get("optimization_mode")),
        ("optimizationSwitchState", optimization.get("switch_state")),
        ("optimizationSupportsSwitching", optimization.get("supports_switching")),
        ("optimizationRequiresOverride", optimization.get("requires_override")),
    ):
        if text := str(value).strip() if value is not None else "":
            props[key] = text

    supported_modes = optimization.get("supported_optimization_modes")
    if isinstance(supported_modes, list):
        modes = [
            str(mode).strip().upper()
            for mode in supported_modes
            if str(mode or "").strip()
        ]
        if modes:
            props["optimizationSupportedModes"] = ",".join(modes)

    return props


def _hems_device_status(payload: dict[str, Any]) -> str:
    state = str(payload.get("state_device") or payload.get("connectivity_status") or "").strip().upper()
    if state in {"OK", "ONLINE", "CONNECTED"}:
        return "ONLINE"
    if state in {"OFFLINE", "DISCONNECTED"}:
        return "OFFLINE"
    return state or "UNKNOWN"


def _hems_kind_title(kind: str) -> str:
    return {
        "battery": "KiwiGrid HEMS Battery",
        "pv_plant": "KiwiGrid HEMS PV Plant",
        "evstation": "KiwiGrid HEMS EV Station",
        "plug": "KiwiGrid HEMS Plug",
        "device": "KiwiGrid HEMS Device",
        "analytics_consumption": "KiwiGrid Stats",
        "analytics_production": "KiwiGrid Stats",
        "analytics_storage": "KiwiGrid Stats",
        "analytics_independence": "KiwiGrid Stats",
        "analytics_finance": "KiwiGrid Stats",
    }.get(kind, "KiwiGrid HEMS")


def _hems_kind_endpoint(kind: str) -> str:
    return {
        "battery": "/v11/battery",
        "pv_plant": "/v11/pv-plant",
        "evstation": "/v11/evstation",
        "plug": "/v11/plug",
        "device": "/v11/device",
        "analytics_consumption": "/v11/analytics/consumption",
        "analytics_production": "/v11/analytics/production",
        "analytics_storage": "/v11/analytics/storage",
        "analytics_independence": "/v11/analytics/independence",
        "analytics_finance": "/v11/analytics/finance",
    }.get(kind, "/v11")

# Shared item helpers ------------------------------------------------------


def _hems_common_device_items(prefix: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return common HEMS item sensors.

    Device metadata such as name, manufacturer, model, serial number and
    firmware is intentionally not exposed as separate entities. It is mapped
    to Home Assistant DeviceInfo via hems_payloads_to_things() instead.
    """
    return [
        _diagnostic_string_item(prefix, "type", payload.get("type")),
        _diagnostic_string_item(prefix, "state_device", payload.get("state_device")),
        _bool_item(prefix, "configured_in_location", payload.get("configured_in_location")),
    ] + _hems_optimization_items(prefix, payload)


def _hems_optimization_items(prefix: str, payload: dict[str, Any]) -> list[dict[str, Any] | None]:
    optimization = payload.get("optimization")
    if not isinstance(optimization, dict):
        return []
    config = optimization.get("config")
    config = config if isinstance(config, dict) else {}
    return [
        _diagnostic_string_item(prefix, "optimization_mode", config.get("optimization_mode")),
        _diagnostic_string_item(prefix, "switch_state", optimization.get("switch_state")),
        _diagnostic_bool_item(prefix, "schedule_exists", optimization.get("schedule_exists")),
        _diagnostic_bool_item(prefix, "supports_switching", optimization.get("supports_switching")),
        _diagnostic_bool_item(prefix, "requires_override", optimization.get("requires_override")),
    ]


def _known_specific_device_ids(
    *,
    batteries: list[dict[str, Any]] | None,
    pv_plants: list[dict[str, Any]] | None,
    evstations: list[dict[str, Any]] | None,
    plugs: list[dict[str, Any]] | None,
) -> set[str]:
    ids: set[str] = set()
    for payloads in (batteries, pv_plants, evstations, plugs):
        for payload in payloads or []:
            if payload_id := _payload_id(payload):
                ids.add(payload_id)
    return ids


def _payloads_by_id(payloads: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        payload_id: payload
        for payload in payloads
        if (payload_id := _payload_id(payload))
    }


def _device_names_by_id(
    *,
    batteries: Iterable[dict[str, Any]] | None = None,
    devices: Iterable[dict[str, Any]] | None = None,
    device_optimizations: Iterable[dict[str, Any]] | None = None,
    pv_plants: Iterable[dict[str, Any]] | None = None,
    evstations: Iterable[dict[str, Any]] | None = None,
    plugs: Iterable[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Return HEMS device display names keyed by KiwiGrid device id."""
    names: dict[str, str] = {}
    for payloads in (devices, device_optimizations, batteries, pv_plants, evstations, plugs):
        for payload in payloads or ():
            if not isinstance(payload, Mapping):
                continue
            payload_id = _payload_id(dict(payload))
            name = str(payload.get("name") or "").strip()
            if payload_id and name:
                names[payload_id] = name
    return names


def hems_device_names_by_id(
    *,
    batteries: Iterable[dict[str, Any]] | None = None,
    devices: Iterable[dict[str, Any]] | None = None,
    device_optimizations: Iterable[dict[str, Any]] | None = None,
    pv_plants: Iterable[dict[str, Any]] | None = None,
    evstations: Iterable[dict[str, Any]] | None = None,
    plugs: Iterable[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Return HEMS device display names keyed by KiwiGrid device id."""
    return _device_names_by_id(
        batteries=batteries,
        devices=devices,
        device_optimizations=device_optimizations,
        pv_plants=pv_plants,
        evstations=evstations,
        plugs=plugs,
    )


def _merge_optimization_payloads(
    payloads: Iterable[dict[str, Any]],
    optimization_by_id: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_payloads: list[dict[str, Any]] = []
    for payload in payloads:
        optimization = optimization_by_id.get(_payload_id(payload) or "")
        if not optimization:
            merged_payloads.append(payload)
            continue
        merged = dict(payload)
        merged["optimization"] = optimization
        merged_payloads.append(merged)
    return merged_payloads


def _daily_analytics_time_window(
    *,
    from_time: datetime | None,
    to_time: datetime | None,
) -> tuple[datetime, datetime]:
    now = datetime.now().astimezone()
    start = from_time or now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = to_time or now.replace(hour=23, minute=59, second=59, microsecond=0)
    if start.tzinfo is None:
        start = start.astimezone()
    if end.tzinfo is None:
        end = end.astimezone()
    return start, end


def _year_to_date_time_window(
    *,
    from_time: datetime | None,
    to_time: datetime | None,
) -> tuple[datetime, datetime]:
    now = datetime.now().astimezone()
    start = from_time or now.replace(
        month=1,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    end = to_time or now.replace(hour=23, minute=59, second=0, microsecond=0)
    if start.tzinfo is None:
        start = start.astimezone()
    if end.tzinfo is None:
        end = end.astimezone()
    return start, end


def _month_to_date_time_window(
    *,
    from_time: datetime | None,
    to_time: datetime | None,
) -> tuple[datetime, datetime]:
    now = datetime.now().astimezone()
    start = from_time or now.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    end = to_time or now.replace(hour=23, minute=59, second=59, microsecond=0)
    if start.tzinfo is None:
        start = start.astimezone()
    if end.tzinfo is None:
        end = end.astimezone()
    return start, end


def _work_summary_time_window(
    *,
    period: str,
    from_time: datetime | None,
    to_time: datetime | None,
) -> tuple[datetime, datetime]:
    if period == "today":
        return _daily_analytics_time_window(from_time=from_time, to_time=to_time)
    if period == "month":
        return _month_to_date_time_window(from_time=from_time, to_time=to_time)
    return _year_to_date_time_window(from_time=from_time, to_time=to_time)


def _format_analytics_time(value: datetime) -> str:
    return value.replace(microsecond=0, tzinfo=None).isoformat(timespec="seconds")


def _analytics_payload(
    kind: str,
    payload: dict[str, Any],
    *,
    period_id: str = "today",
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("id", period_id)
    normalized.setdefault("name", "KiwiGrid Stats")
    normalized.setdefault("type", kind.upper())
    if user_profile:
        normalized["user_profile"] = dict(user_profile)
    return normalized


def _analytics_unit_type_scale(
    value: Any,
    *,
    aggregated: bool,
    currency: str = "",
) -> tuple[str, str, float]:
    unit = str(value or "").strip().upper()
    if unit in {"W", "WATT"}:
        return (
            "Wh" if aggregated else "W",
            "Number:Energy" if aggregated else "Number:Power",
            1,
        )
    if unit in {"WH", "WATTHOUR", "WATT_HOUR"}:
        return "kWh", "Number:Energy", 0.001
    if unit in {"%", "PERCENT", "PERCENTAGE"}:
        return "%", "Number", 1
    if unit in {"CENT", "CENTS"}:
        return currency or "EUR", "Number", 0.01
    if unit in {"CURRENCY", "MONEY"}:
        return currency or "", "Number", 1
    if unit in {"", "UNKNOWN"}:
        return "", "Number", 1
    return str(value).strip(), "Number", 1


def _profile_currency(profile: Mapping[str, Any] | None) -> str:
    if not isinstance(profile, Mapping):
        return ""
    return str(profile.get("currency") or "").strip().upper()


def _latest_timeseries_value(values: Any) -> tuple[str, Any] | None:
    if not isinstance(values, dict):
        return None

    valid_values = [
        (str(timestamp), value)
        for timestamp, value in values.items()
        if timestamp and value is not None
    ]
    if not valid_values:
        return None
    return max(valid_values, key=lambda item: item[0])


def _payload_id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("uuid") or "").strip()


def _hems_prefix(kind: str, payload: dict[str, Any]) -> str:
    raw_id = str(payload.get("id") or payload.get("uuid") or payload.get("serial_number") or "unknown")
    safe_id = _slug(raw_id)
    return f"hems_{kind}_{safe_id}"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "unknown"


def _string_item(prefix: str, suffix: str, value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    return _with_entity_category(
        {
            "name": f"{prefix}_{suffix}",
            "label": suffix.replace("_", " ").title(),
            "state": str(value),
            "type": "String",
            "editable": False,
            "category": "kiwigrid_hems",
        },
        None,
    )


def _diagnostic_string_item(prefix: str, suffix: str, value: Any) -> dict[str, Any] | None:
    item = _string_item(prefix, suffix, value)
    return _with_entity_category(item, "diagnostic")


def _with_entity_category(
    item: dict[str, Any] | None,
    entity_category: str | None,
) -> dict[str, Any] | None:
    if item is not None and entity_category:
        item["entityCategory"] = entity_category
    return item


def _bool_item(prefix: str, suffix: str, value: Any) -> dict[str, Any] | None:
    if not isinstance(value, bool):
        return None
    return {
        "name": f"{prefix}_{suffix}",
        "label": suffix.replace("_", " ").title(),
        "state": "true" if value else "false",
        "type": "String",
        "editable": False,
        "category": "kiwigrid_hems",
    }


def _diagnostic_bool_item(prefix: str, suffix: str, value: Any) -> dict[str, Any] | None:
    item = _bool_item(prefix, suffix, value)
    return _with_entity_category(item, "diagnostic")


def _number_item(
    prefix: str,
    suffix: str,
    value: Any,
    unit: str,
    item_type: str,
    *,
    scale: float = 1,
    label: str | None = None,
) -> dict[str, Any] | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value) * scale
    except (TypeError, ValueError):
        return None
    unit_suffix = f" {unit}" if unit else ""
    if numeric.is_integer():
        state = f"{int(numeric)}{unit_suffix}"
    else:
        state = f"{numeric:.3f}".rstrip("0").rstrip(".") + unit_suffix
    return {
        "name": f"{prefix}_{suffix}",
        "label": label or suffix.replace("_", " ").title(),
        "state": state,
        "type": item_type,
        "editable": False,
        "category": "kiwigrid_hems",
        "stateDescription": {"pattern": f"%.2f{unit_suffix}"},
    }


def _value_from_unit_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value")
    return value


def _nested_number(payload: Mapping[str, Any], *path: str) -> float | None:
    value: Any = payload
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_value(payload: Mapping[str, Any], *path: str) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _date_ms_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        timestamp = int(value) / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)
