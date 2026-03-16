from __future__ import annotations

from collections.abc import Mapping
import ipaddress
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_ENABLE_ALL_SENSORS,
    CONF_ENERGY_DELTA_KWH,
    CONF_HOST,
    CONF_NAME_PREFIX,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_ENABLE_ALL_SENSORS,
    DEFAULT_ENERGY_DELTA_KWH,
    DEFAULT_NAME_PREFIX,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_ENERGY_DELTA_KWH,
    MIN_SCAN_INTERVAL,
)
from .coordinator import (
    SOLARWATTClient,
    SolarwattAuthError,
    SolarwattConnectionError,
    SolarwattNotManagerError,
    SolarwattProtocolError,
)
from .entity_helpers import sync_enable_all_item_sensor_entities

_LOGGER = logging.getLogger(__name__)
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _normalize_host(raw_host: str | None) -> str | None:
    """Normalize and validate host input (hostname/IPv4, optional :port, no URL)."""
    host = str(raw_host or "").strip().lower()
    if not host:
        return None

    if "://" in host:
        return None
    if any(ch in host for ch in ("/", "?", "#", "@")):
        return None
    if any(ch.isspace() for ch in host):
        return None

    host_part = host
    port_part = None
    if ":" in host:
        if host.count(":") > 1:
            return None
        host_part, port_part = host.rsplit(":", 1)
        if not host_part or not port_part or not port_part.isdigit():
            return None

    try:
        ip = ipaddress.ip_address(host_part)
    except ValueError:
        ip = None

    if ip is not None:
        if ip.version != 4:
            return None
        return f"{host_part}:{port_part}" if port_part is not None else host_part

    if (
        len(host_part) > 253
        or host_part.startswith(".")
        or host_part.endswith(".")
        or ".." in host_part
    ):
        return None

    labels = host_part.split(".")
    if any(not _HOST_LABEL_RE.fullmatch(label) for label in labels):
        return None
    return f"{host_part}:{port_part}" if port_part is not None else host_part


def _normalize_text(value: Any) -> str:
    """Normalize free-text form values."""
    return str(value or "").strip()


def _normalize_bool(value: Any, *, default: bool) -> bool:
    """Normalize boolean form values."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _normalize_int(value: Any, *, default: int) -> int | None:
    """Normalize integer form values."""
    raw_value = default if value is None else value
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _normalize_float(value: Any, *, default: float) -> float | None:
    """Normalize float form values."""
    raw_value = default if value is None else value
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _normalize_options_input(
    user_input: Mapping[str, Any],
    current_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize user-visible options while preserving internal option keys."""
    current = dict(current_options or {})
    return {
        **current,
        CONF_SCAN_INTERVAL: _normalize_int(
            user_input.get(
                CONF_SCAN_INTERVAL,
                current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ),
            default=DEFAULT_SCAN_INTERVAL,
        ),
        CONF_ENERGY_DELTA_KWH: _normalize_float(
            user_input.get(
                CONF_ENERGY_DELTA_KWH,
                current.get(CONF_ENERGY_DELTA_KWH, DEFAULT_ENERGY_DELTA_KWH),
            ),
            default=DEFAULT_ENERGY_DELTA_KWH,
        ),
        CONF_NAME_PREFIX: _normalize_text(
            user_input.get(
                CONF_NAME_PREFIX,
                current.get(CONF_NAME_PREFIX, DEFAULT_NAME_PREFIX),
            )
        ),
        CONF_ENABLE_ALL_SENSORS: _normalize_bool(
            user_input.get(
                CONF_ENABLE_ALL_SENSORS,
                current.get(CONF_ENABLE_ALL_SENSORS, DEFAULT_ENABLE_ALL_SENSORS),
            ),
            default=DEFAULT_ENABLE_ALL_SENSORS,
        ),
    }


def _normalize_user_input(user_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize config-entry data and options from the user step."""
    entry_data = {
        CONF_HOST: _normalize_host(user_input.get(CONF_HOST)),
        CONF_USERNAME: _normalize_text(user_input.get(CONF_USERNAME)),
        CONF_PASSWORD: _normalize_text(user_input.get(CONF_PASSWORD)),
    }
    options = _normalize_options_input(user_input)
    return entry_data, options


def _validate_options_data(options: Mapping[str, Any]) -> dict[str, str]:
    """Validate normalized option values."""
    errors: dict[str, str] = {}

    scan_interval = options.get(CONF_SCAN_INTERVAL)
    if (
        scan_interval is None
        or scan_interval < MIN_SCAN_INTERVAL
        or scan_interval > MAX_SCAN_INTERVAL
    ):
        errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"

    energy_delta = options.get(CONF_ENERGY_DELTA_KWH)
    if energy_delta is None or energy_delta < MIN_ENERGY_DELTA_KWH:
        errors[CONF_ENERGY_DELTA_KWH] = "invalid_energy_delta_kwh"

    return errors


def _validate_user_data(
    entry_data: Mapping[str, Any],
    options: Mapping[str, Any],
) -> dict[str, str]:
    """Validate normalized user-step data."""
    errors = _validate_options_data(options)

    if entry_data.get(CONF_HOST) is None:
        errors[CONF_HOST] = "invalid_host"
    if not entry_data.get(CONF_USERNAME):
        errors[CONF_USERNAME] = "invalid_username"
    if not entry_data.get(CONF_PASSWORD):
        errors[CONF_PASSWORD] = "invalid_password"

    return errors


class SOLARWATTItemsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def _build_user_schema(
        self, user_input: Mapping[str, Any] | None = None
    ) -> vol.Schema:
        """Build the user-step schema."""
        values = dict(user_input or {})
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=values.get(CONF_HOST, "")): str,
                vol.Required(
                    CONF_USERNAME,
                    default=values.get(CONF_USERNAME, "installer"),
                ): str,
                vol.Required(CONF_PASSWORD, default=values.get(CONF_PASSWORD, "")): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_ENERGY_DELTA_KWH,
                    default=values.get(
                        CONF_ENERGY_DELTA_KWH,
                        DEFAULT_ENERGY_DELTA_KWH,
                    ),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_NAME_PREFIX,
                    default=values.get(CONF_NAME_PREFIX, DEFAULT_NAME_PREFIX),
                ): str,
                vol.Optional(
                    CONF_ENABLE_ALL_SENSORS,
                    default=values.get(
                        CONF_ENABLE_ALL_SENSORS,
                        DEFAULT_ENABLE_ALL_SENSORS,
                    ),
                ): bool,
            }
        )

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            entry_data, options = _normalize_user_input(user_input)
            errors = _validate_user_data(entry_data, options)

            if not errors:
                host = entry_data[CONF_HOST]
                if host is None:
                    errors[CONF_HOST] = "invalid_host"
                else:
                    errors = await self._test_connection(
                        host=host,
                        username=entry_data[CONF_USERNAME],
                        password=entry_data[CONF_PASSWORD],
                    )

            if not errors:
                host = entry_data[CONF_HOST]
                if host is None:
                    errors[CONF_HOST] = "invalid_host"
                else:
                    await self.async_set_unique_id(host)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"SOLARWATT ({host})",
                        data=entry_data,
                        options=options,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_user_schema(user_input),
            errors=errors,
        )

    async def _test_connection(
        self,
        *,
        host: str,
        username: str,
        password: str,
    ) -> dict[str, str]:
        """Test connection to SOLARWATT Manager using normalized credentials."""
        errors: dict[str, str] = {}

        try:
            client = SOLARWATTClient(
                self.hass,
                host=host,
                username=username,
                password=password,
            )
            try:
                await client.async_probe_manager()
                await client.async_validate_connection()
            finally:
                await client.async_close()
        except ValueError as err:
            _LOGGER.warning("Invalid input for SOLARWATT Manager: %s", err)
            errors["base"] = "invalid_input"
        except SolarwattNotManagerError as err:
            _LOGGER.warning("Host is not a SOLARWATT Manager: %s", err)
            errors["base"] = "not_solarwatt"
        except SolarwattAuthError as err:
            _LOGGER.warning("Invalid SOLARWATT credentials: %s", err)
            errors["base"] = "invalid_auth"
        except SolarwattConnectionError as err:
            _LOGGER.warning("Connection error to SOLARWATT Manager: %s", err)
            errors["base"] = "cannot_connect"
        except SolarwattProtocolError as err:
            _LOGGER.warning("Unexpected SOLARWATT response: %s", err)
            errors["base"] = "connection_failed"
        except Exception as err:
            _LOGGER.exception(
                "Unexpected error testing SOLARWATT connection: %s",
                err,
            )
            errors["base"] = "unknown_error"

        return errors

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SOLARWATTItemsOptionsFlow(config_entry)


class SOLARWATTItemsOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        # Home Assistant exposes `config_entry` as a read-only property on
        # OptionsFlow (no setter). Store the entry in the internal attribute
        # expected by the base class so this works across HA versions.
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            data = self._build_options_data(user_input)
            errors = _validate_options_data(data)

            if not errors:
                sync_enable_all_item_sensor_entities(
                    self.hass,
                    self.config_entry,
                    data,
                )
                return self.async_create_entry(title="", data=data)

            return self.async_show_form(
                step_id="init",
                data_schema=self._build_options_schema(user_input),
                errors=errors,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_options_schema(),
        )

    def _build_options_schema(
        self, user_input: Mapping[str, Any] | None = None
    ) -> vol.Schema:
        """Build the options schema."""
        values = dict(user_input or self.config_entry.options)
        return vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_ENERGY_DELTA_KWH,
                    default=values.get(
                        CONF_ENERGY_DELTA_KWH,
                        DEFAULT_ENERGY_DELTA_KWH,
                    ),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_NAME_PREFIX,
                    default=values.get(CONF_NAME_PREFIX, DEFAULT_NAME_PREFIX),
                ): str,
                vol.Optional(
                    CONF_ENABLE_ALL_SENSORS,
                    default=values.get(
                        CONF_ENABLE_ALL_SENSORS,
                        DEFAULT_ENABLE_ALL_SENSORS,
                    ),
                ): bool,
            }
        )

    def _build_options_data(self, user_input: Mapping[str, Any]) -> dict[str, Any]:
        """Merge, normalize, and return user-visible options."""
        return _normalize_options_input(user_input, self.config_entry.options)
