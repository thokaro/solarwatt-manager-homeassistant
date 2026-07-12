from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import ipaddress
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from .const import (
    CONF_DISABLE_DUPLICATE_ITEM_ENTITIES,
    CONF_ENABLED_THINGS,
    CONF_ENERGY_DELTA_KWH,
    CONF_HOST,
    CONF_KIWIGRID_HEMS_ENABLED,
    CONF_KIWIGRID_HEMS_PASSWORD,
    CONF_KIWIGRID_HEMS_SCAN_INTERVAL,
    CONF_KIWIGRID_HEMS_USERNAME,
    CONF_PASSWORD,
    CONF_POWER_UNAVAILABLE_THRESHOLD,
    CONF_REBUILD_ENTITY_IDS,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_DISABLE_DUPLICATE_ITEM_ENTITIES,
    DEFAULT_ENERGY_DELTA_KWH,
    DEFAULT_KIWIGRID_HEMS_ENABLED,
    DEFAULT_KIWIGRID_HEMS_SCAN_INTERVAL,
    DEFAULT_POWER_UNAVAILABLE_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_ENERGY_DELTA_KWH,
    MIN_POWER_UNAVAILABLE_THRESHOLD,
    MIN_SCAN_INTERVAL,
    get_selected_thing_uids,
    get_thing_display_name,
    get_thing_selection_detail,
)
from .client import (
    SOLARWATTClient,
    SolarwattAuthError,
    SolarwattConnectionError,
    SolarwattNotManagerError,
    SolarwattProtocolError,
)
from .entity_helpers import sync_selected_thing_entities
from .hems_api import is_energy_overview_thing, is_hems_thing, is_kiwigrid_flow_thing
from .registry_migrations import mark_pending_registry_migration
from .thing_matching import (
    is_local_bridge_thing as _is_bridge_type,
    merge_selection_things,
)

_LOGGER = logging.getLogger(__name__)
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_DEVICE_SELECTION_SECTION = "device_selection"
_KIWIGRID_HEMS_THING_UID = "kiwigrid-hems"
_RAW_HOST_KEY = "_raw_host"
_KNOWN_CLIENT_ERRORS: tuple[tuple[type[Exception], str, str], ...] = (
    (ValueError, "invalid_input", "Invalid input while %s: %s"),
    (SolarwattNotManagerError, "not_solarwatt", "Host is not a SOLARWATT Manager while %s: %s"),
    (SolarwattConnectionError, "cannot_connect", "Connection error while %s: %s"),
    (SolarwattProtocolError, "connection_failed", "Unexpected SOLARWATT response while %s: %s"),
)


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


def _normalize_text(value: Any, *, default: str = "") -> str:
    """Normalize free-text form values."""
    raw_value = default if value is None else value
    return str(raw_value).strip()


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


def _normalize_bool(value: Any, *, default: bool) -> bool:
    """Normalize boolean form values."""
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _is_invalid_scan_interval(value: Any) -> bool:
    """Return True if the configured scan interval is outside the allowed range."""
    return value is None or value < MIN_SCAN_INTERVAL or value > MAX_SCAN_INTERVAL


def _is_invalid_energy_delta(value: Any) -> bool:
    """Return True if the configured energy delta is outside the allowed range."""
    return value is None or value < MIN_ENERGY_DELTA_KWH


def _is_invalid_power_unavailable_threshold(value: Any) -> bool:
    """Return True if the power unavailable threshold is outside the allowed range."""
    return value is None or value < MIN_POWER_UNAVAILABLE_THRESHOLD


def _is_never_invalid(_: Any) -> bool:
    """Return False for options without a validation constraint."""
    return False


_OPTION_FIELD_SPECS: tuple[dict[str, Any], ...] = (
    {
        "key": CONF_KIWIGRID_HEMS_ENABLED,
        "default": DEFAULT_KIWIGRID_HEMS_ENABLED,
        "normalize": _normalize_bool,
        "coerce": bool,
        "error": "",
        "invalid": _is_never_invalid,
    },
    {
        "key": CONF_KIWIGRID_HEMS_USERNAME,
        "default": "",
        "normalize": _normalize_text,
        "coerce": str,
        "error": "",
        "invalid": _is_never_invalid,
    },
    {
        "key": CONF_KIWIGRID_HEMS_PASSWORD,
        "default": "",
        "normalize": _normalize_text,
        "coerce": str,
        "error": "",
        "invalid": _is_never_invalid,
    },
    {
        "key": CONF_KIWIGRID_HEMS_SCAN_INTERVAL,
        "default": DEFAULT_KIWIGRID_HEMS_SCAN_INTERVAL,
        "normalize": _normalize_int,
        "coerce": vol.Coerce(int),
        "error": "invalid_scan_interval",
        "invalid": _is_invalid_scan_interval,
    },
    {
        "key": CONF_SCAN_INTERVAL,
        "default": DEFAULT_SCAN_INTERVAL,
        "normalize": _normalize_int,
        "coerce": vol.Coerce(int),
        "error": "invalid_scan_interval",
        "invalid": _is_invalid_scan_interval,
    },
    {
        "key": CONF_ENERGY_DELTA_KWH,
        "default": DEFAULT_ENERGY_DELTA_KWH,
        "normalize": _normalize_float,
        "coerce": vol.Coerce(float),
        "error": "invalid_energy_delta_kwh",
        "invalid": _is_invalid_energy_delta,
    },
    {
        "key": CONF_POWER_UNAVAILABLE_THRESHOLD,
        "default": DEFAULT_POWER_UNAVAILABLE_THRESHOLD,
        "normalize": _normalize_int,
        "coerce": vol.Coerce(int),
        "error": "invalid_power_unavailable_threshold",
        "invalid": _is_invalid_power_unavailable_threshold,
    },
    {
        "key": CONF_DISABLE_DUPLICATE_ITEM_ENTITIES,
        "default": DEFAULT_DISABLE_DUPLICATE_ITEM_ENTITIES,
        "normalize": _normalize_bool,
        "coerce": bool,
        "error": "",
        "invalid": _is_never_invalid,
    },
)


def _build_option_schema_fields(values: Mapping[str, Any]) -> dict[Any, Any]:
    """Build voluptuous schema fields for all user-visible options."""
    return {
        vol.Optional(
            field["key"],
            default=values.get(field["key"], field["default"]),
        ): field["coerce"]
        for field in _OPTION_FIELD_SPECS
    }


def _normalize_options_input(
    user_input: Mapping[str, Any],
    current_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize user-visible options."""
    current = dict(current_options or {})
    return {
        field["key"]: field["normalize"](
            user_input.get(
                field["key"],
                current.get(field["key"], field["default"]),
            ),
            default=field["default"],
        )
        for field in _OPTION_FIELD_SPECS
    }


def _normalize_user_input(user_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize config-entry data and options from the user step."""
    raw_host = _normalize_text(user_input.get(CONF_HOST))
    entry_data = {
        CONF_HOST: _normalize_host(raw_host),
        _RAW_HOST_KEY: raw_host,
        CONF_USERNAME: _normalize_text(user_input.get(CONF_USERNAME)),
        CONF_PASSWORD: _normalize_text(user_input.get(CONF_PASSWORD)),
    }
    options = _normalize_options_input(user_input)
    return entry_data, options


def _normalize_options_entry_data(
    user_input: Mapping[str, Any],
    current_data: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize config-entry data from the options step."""
    raw_host = _normalize_text(
        user_input.get(CONF_HOST, current_data.get(CONF_HOST, ""))
    )
    return {
        CONF_HOST: _normalize_host(raw_host),
        _RAW_HOST_KEY: raw_host,
        CONF_USERNAME: _normalize_text(
            user_input.get(CONF_USERNAME, current_data.get(CONF_USERNAME, "installer"))
        ),
        CONF_PASSWORD: _normalize_text(
            user_input.get(CONF_PASSWORD, current_data.get(CONF_PASSWORD, ""))
        ),
    }


def _validate_options_data(options: Mapping[str, Any]) -> dict[str, str]:
    """Validate normalized option values."""
    errors = {
        field["key"]: field["error"]
        for field in _OPTION_FIELD_SPECS
        if field["invalid"](options.get(field["key"]))
    }
    if options.get(CONF_KIWIGRID_HEMS_ENABLED):
        if not str(options.get(CONF_KIWIGRID_HEMS_USERNAME) or "").strip():
            errors[CONF_KIWIGRID_HEMS_USERNAME] = "invalid_username"
        if not str(options.get(CONF_KIWIGRID_HEMS_PASSWORD) or "").strip():
            errors[CONF_KIWIGRID_HEMS_PASSWORD] = "invalid_password"
    return errors


def _validate_user_data(
    entry_data: Mapping[str, Any],
    options: Mapping[str, Any],
) -> dict[str, str]:
    """Validate normalized user-step data."""
    errors = _validate_options_data(options)

    local_host = entry_data.get(CONF_HOST)
    local_username = str(entry_data.get(CONF_USERNAME) or "").strip()
    local_password = str(entry_data.get(CONF_PASSWORD) or "").strip()
    hems_enabled = bool(options.get(CONF_KIWIGRID_HEMS_ENABLED))
    hems_username = str(options.get(CONF_KIWIGRID_HEMS_USERNAME) or "").strip()
    hems_password = str(options.get(CONF_KIWIGRID_HEMS_PASSWORD) or "").strip()

    if local_host is None and str(entry_data.get(_RAW_HOST_KEY) or "").strip():
        errors[CONF_HOST] = "invalid_host"
    if local_host and not local_username:
        errors[CONF_USERNAME] = "invalid_username"
    if local_host and not local_password:
        errors[CONF_PASSWORD] = "invalid_password"
    if hems_enabled and not hems_username:
        errors[CONF_KIWIGRID_HEMS_USERNAME] = "invalid_username"
    if hems_enabled and not hems_password:
        errors[CONF_KIWIGRID_HEMS_PASSWORD] = "invalid_password"
    if not local_host and not hems_enabled:
        errors["base"] = "missing_connection"

    return errors


def _selected_checkbox_uids(
    device_fields: Mapping[str, str],
    user_input: Mapping[str, Any],
) -> list[str]:
    """Return selected thing UIDs from checkbox inputs."""
    checkbox_values = user_input.get(_DEVICE_SELECTION_SECTION)
    if not isinstance(checkbox_values, Mapping):
        checkbox_values = user_input

    return [
        uid
        for field_name, uid in device_fields.items()
        if bool(checkbox_values.get(field_name))
    ]


def _build_thing_checkbox_schema(
    things: list[tuple[str, dict[str, Any]]],
    selected_uids: set[str],
) -> tuple[dict[Any, Any], dict[str, str]]:
    """Build checkbox fields for a list of things and return field-to-UID mapping."""
    device_fields: dict[str, str] = {}
    schema: dict[Any, Any] = {}
    for uid, thing in things:
        field_name = SOLARWATTItemsConfigFlow._thing_checkbox_label(uid, thing, device_fields)
        device_fields[field_name] = uid
        schema[
            vol.Optional(
                field_name,
                default=(
                    is_energy_overview_thing(thing)
                    or is_kiwigrid_flow_thing(thing)
                    or uid in selected_uids
                ),
            )
        ] = bool
    return schema, device_fields


def _build_thing_checkbox_section_schema(
    things: list[tuple[str, dict[str, Any]]],
    selected_uids: set[str],
) -> tuple[dict[Any, Any], dict[str, str]]:
    """Build a named section containing thing checkbox fields."""
    checkbox_schema, device_fields = _build_thing_checkbox_schema(things, selected_uids)
    return {
        vol.Required(_DEVICE_SELECTION_SECTION): section(
            vol.Schema(checkbox_schema),
            {"collapsed": True},
        )
    }, device_fields


def _merge_selection_things(
    base_things: Mapping[str, dict[str, Any]],
    incoming_things: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge duplicate local/HEMS things for one selection checkbox per device."""
    return merge_selection_things(
        base_things,
        incoming_things,
        is_hems_thing=is_hems_thing,
        is_bridge_thing=_is_local_bridge_thing,
    )


def _is_local_bridge_thing(thing: Mapping[str, Any]) -> bool:
    """Return True for local HEMS configurator bridge/container things."""
    return is_hems_thing(thing) and _is_bridge_type(thing)


def _kiwigrid_hems_selection_thing() -> dict[str, Any]:
    """Return the synthetic KiwiGrid Stats device used during device selection."""
    return {
        "UID": _KIWIGRID_HEMS_THING_UID,
        "uid": _KIWIGRID_HEMS_THING_UID,
        "label": "KiwiGrid Stats",
        "thingTypeUID": "kiwigrid-hems:analytics_consumption",
        "thingTypeUid": "kiwigrid-hems:analytics_consumption",
        "statusInfo": {"status": "UNKNOWN", "statusDetail": "NONE"},
        "properties": {
            "thingTypeTitle": "KiwiGrid Stats",
            "thingTypeCategory": "KIWIGRID_HEMS",
            "kiwigridEndpoint": "/v11/analytics/consumption",
            "kiwigridKind": "analytics_consumption",
            "generatedLabel": "KiwiGrid HEMS v11",
            "model": "KiwiGrid HEMS v11",
        },
        "channels": [
            {
                "id": "hems_analytics_consumption",
                "uid": f"{_KIWIGRID_HEMS_THING_UID}:hems_analytics_consumption",
                "label": "HEMS analytics",
                "itemType": "Number:Energy",
                "linkedItems": [
                    "hems_analytics_consumption_today_consumption_powerconsumed"
                ],
                "properties": {
                    "kiwigrid.endpoint": "/v11/analytics/consumption",
                    "kiwigrid.kind": "analytics_consumption",
                    "kig.meta.scope": "kiwigrid_hems",
                },
            }
        ],
    }


class SOLARWATTItemsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._pending_entry_data: dict[str, Any] | None = None
        self._pending_options: dict[str, Any] | None = None
        self._available_things: dict[str, dict[str, Any]] = {}
        self._device_fields: dict[str, str] = {}

    def _build_user_schema(
        self, user_input: Mapping[str, Any] | None = None
    ) -> vol.Schema:
        """Build the user-step schema."""
        values = dict(user_input or {})
        return vol.Schema(
            {
                vol.Optional(CONF_HOST, default=values.get(CONF_HOST, "")): str,
                vol.Optional(
                    CONF_USERNAME,
                    default=values.get(CONF_USERNAME, "installer"),
                ): str,
                vol.Optional(CONF_PASSWORD, default=values.get(CONF_PASSWORD, "")): str,
                **_build_option_schema_fields(values),
            }
        )

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        things: dict[str, dict[str, Any]] = {}

        if user_input is not None:
            entry_data, options = _normalize_user_input(user_input)
            errors = _validate_user_data(entry_data, options)
            host = entry_data.get(CONF_HOST)

            if not errors and host is not None:
                _, errors = await self._async_with_client(
                    host=host,
                    username=entry_data[CONF_USERNAME],
                    password=entry_data[CONF_PASSWORD],
                    action=SOLARWATTClient.async_validate_connection,
                    action_label="testing SOLARWATT connection",
                )

            if not errors and host is not None:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                things, errors = await self._async_fetch_things(
                    host=host,
                    username=entry_data[CONF_USERNAME],
                    password=entry_data[CONF_PASSWORD],
                )
                things = _merge_selection_things({}, things)
            elif not errors:
                await self.async_set_unique_id("kiwigrid_hems")
                self._abort_if_unique_id_configured()

            if not errors and options.get(CONF_KIWIGRID_HEMS_ENABLED):
                hems_things, errors = await self._async_fetch_hems_things(
                    username=options[CONF_KIWIGRID_HEMS_USERNAME],
                    password=options[CONF_KIWIGRID_HEMS_PASSWORD],
                    include_energy_flow=True,
                )
                things = _merge_selection_things(things, hems_things)

            if not errors:
                selectable_things = self._selectable_things(things)
                if options.get(CONF_KIWIGRID_HEMS_ENABLED):
                    selectable_things.setdefault(
                        _KIWIGRID_HEMS_THING_UID,
                        _kiwigrid_hems_selection_thing(),
                    )
                self._pending_entry_data = entry_data
                self._pending_options = options
                self._available_things = selectable_things
                if not selectable_things:
                    return self._async_create_config_entry([] if things else None)
                return await self.async_step_devices()

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_user_schema(user_input),
            errors=errors,
        )

    async def async_step_devices(self, user_input=None):
        if self._pending_entry_data is None or self._pending_options is None:
            return await self.async_step_user()

        if user_input is not None:
            selected = _selected_checkbox_uids(self._device_fields, user_input)
            return self._async_create_config_entry(selected)

        return self.async_show_form(
            step_id="devices",
            data_schema=self._build_devices_schema(),
        )

    def _build_devices_schema(self) -> vol.Schema:
        """Build the device-selection schema."""
        schema, self._device_fields = _build_thing_checkbox_schema(
            self._sorted_things(self._available_things),
            set(self._default_selected_things(self._available_things)),
        )
        return vol.Schema(schema)

    def _async_create_config_entry(self, selected_thing_uids: list[str] | None):
        """Create the config entry using the pending validated data."""
        assert self._pending_entry_data is not None
        assert self._pending_options is not None

        host = self._pending_entry_data[CONF_HOST]
        entry_data = {
            key: value
            for key, value in self._pending_entry_data.items()
            if key != _RAW_HOST_KEY
        }
        options = dict(self._pending_options)
        if selected_thing_uids is None:
            options.pop(CONF_ENABLED_THINGS, None)
        else:
            options[CONF_ENABLED_THINGS] = selected_thing_uids
        title = f"SOLARWATT ({host})" if host else "SOLARWATT KiwiGrid HEMS"
        return self.async_create_entry(
            title=title,
            data=entry_data,
            options=options,
        )

    async def _async_fetch_things(
        self,
        *,
        host: str,
        username: str,
        password: str,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """Fetch device metadata for the device selection step."""
        things_by_uid: dict[str, dict[str, Any]] = {}
        result, errors = await self._async_with_client(
            host=host,
            username=username,
            password=password,
            action=SOLARWATTClient.async_get_things,
            action_label="fetching SOLARWATT things",
        )
        if errors:
            return things_by_uid, errors

        things_by_uid = {
            uid: thing
            for idx, thing in enumerate(result or [])
            if (uid := str(thing.get("UID") or thing.get("uid") or f"unknown_{idx}").strip())
        }

        return things_by_uid, errors

    async def _async_fetch_hems_things(
        self,
        *,
        username: str,
        password: str,
        include_energy_flow: bool = False,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """Fetch KiwiGrid HEMS device metadata for the device selection step."""
        things_by_uid: dict[str, dict[str, Any]] = {}
        result, errors = await self._async_with_client(
            host="",
            username="",
            password="",
            action=lambda client: client.async_get_hems_things(
                username=username,
                password=password,
                include_energy_flow=include_energy_flow,
            ),
            action_label="fetching KiwiGrid HEMS devices",
            auth_error_code="invalid_hems_auth",
        )
        if errors:
            return things_by_uid, errors

        things_by_uid = {
            uid: thing
            for idx, thing in enumerate(result or [])
            if (uid := str(thing.get("UID") or thing.get("uid") or f"hems_unknown_{idx}").strip())
        }

        return things_by_uid, errors

    async def _async_with_client(
        self,
        *,
        host: str,
        username: str,
        password: str,
        action: Callable[[SOLARWATTClient], Awaitable[Any]],
        action_label: str,
        auth_error_code: str = "invalid_local_auth",
    ) -> tuple[Any | None, dict[str, str]]:
        """Run one client action and map known failures to config-flow errors."""
        try:
            client = SOLARWATTClient(
                self.hass,
                host=host,
                username=username,
                password=password,
            )
            try:
                return await action(client), {}
            finally:
                await client.async_close()
        except SolarwattAuthError as err:
            _LOGGER.warning("Invalid SOLARWATT credentials while %s: %s", action_label, err)
            return None, {"base": auth_error_code}
        except Exception as err:
            for error_type, error_code, log_message in _KNOWN_CLIENT_ERRORS:
                if isinstance(err, error_type):
                    _LOGGER.warning(log_message, action_label, err)
                    return None, {"base": error_code}
            _LOGGER.exception("Unexpected error while %s: %s", action_label, err)
            return None, {"base": "unknown_error"}

    @staticmethod
    def _sorted_things(things: Mapping[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
        """Return things sorted by label for stable selector ordering."""
        return sorted(
            things.items(),
            key=lambda item: (
                str(item[1].get("label") or item[0]).strip().lower(),
                item[0],
            ),
        )

    @staticmethod
    def _format_thing_choice(thing: Mapping[str, Any], uid: str) -> str:
        """Return the selector label for one thing."""
        label = get_thing_display_name(thing, uid)
        detail = get_thing_selection_detail(thing)
        if label and detail and detail.lower() != label.lower():
            return f"{label} ({detail})"
        return label or uid

    @staticmethod
    def _thing_has_linked_items(thing: Mapping[str, Any]) -> bool:
        """Return True if any channel of this thing is linked to at least one item."""
        if is_energy_overview_thing(thing) or is_kiwigrid_flow_thing(thing):
            return True
        if _is_local_bridge_thing(thing):
            return False
        if is_hems_thing(thing):
            return True

        channels = thing.get("channels")
        if not isinstance(channels, list):
            return False

        return any(
            isinstance(channel, Mapping)
            and isinstance(linked_items := channel.get("linkedItems"), list)
            and any(str(linked_item).strip() for linked_item in linked_items)
            for channel in channels
        )

    @classmethod
    def _selectable_things(
        cls, things: Mapping[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Return only things that should appear in the device selector."""
        selectable = {
            uid: thing
            for uid, thing in things.items()
            if cls._thing_has_linked_items(thing)
        }
        return _merge_selection_things({}, selectable)

    @classmethod
    def _default_selected_things(cls, things: Mapping[str, dict[str, Any]]) -> list[str]:
        """Return the default-selected devices for a fresh config entry."""
        return [
            uid
            for uid, thing in cls._sorted_things(things)
            if cls._is_default_selected_thing(thing)
        ]

    @staticmethod
    def _is_default_selected_thing(thing: Mapping[str, Any]) -> bool:
        """Return True for things enabled by default during setup."""
        if is_energy_overview_thing(thing) or is_kiwigrid_flow_thing(thing):
            return True

        label = str(thing.get("label") or "").lower()
        thing_type_uid = str(thing.get("thingTypeUID") or thing.get("thingTypeUid") or "").lower()
        properties = thing.get("properties")
        props = properties if isinstance(properties, Mapping) else {}
        ui_category = str(props.get("kig.meta.uiCategory") or "").lower()
        balancing_type = str(props.get("kig.meta.balancingtype") or "").lower()

        is_location = "location" in label or "location" in thing_type_uid
        is_hems = thing_type_uid.startswith("kiwigrid-hems:")
        is_battery = any(
            token in candidate
            for candidate in (label, thing_type_uid, ui_category, balancing_type)
            for token in ("battery", "batteries", "dc_battery")
        )
        return is_location or is_hems or is_battery

    @classmethod
    def _thing_checkbox_label(
        cls,
        uid: str,
        thing: Mapping[str, Any],
        existing_fields: Mapping[str, str],
    ) -> str:
        """Return a stable, user-facing checkbox label for one thing."""
        base = cls._format_thing_choice(thing, uid)
        return base if base not in existing_fields else f"{base} [{uid}]"

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
        self._device_fields: dict[str, str] = {}

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            entry_data = _normalize_options_entry_data(user_input, self.config_entry.data)
            data = self._build_options_data(user_input)
            errors = _validate_user_data(entry_data, data)

            if not errors:
                rebuild_requested = bool(user_input.get(CONF_REBUILD_ENTITY_IDS))
                if rebuild_requested:
                    mark_pending_registry_migration(self.hass, self.config_entry.entry_id)
                coordinator = getattr(self.config_entry, "runtime_data", None)
                if coordinator is not None:
                    sync_selected_thing_entities(
                        self.hass,
                        self.config_entry,
                        coordinator.data,
                        coordinator.item_to_thing_uid,
                        coordinator.things,
                        coordinator.duplicate_item_targets,
                        data,
                    )
                    coordinator.run_discovery_callbacks(data)
                if rebuild_requested:
                    current_options = dict(self.config_entry.options)
                    clean_entry_data = {
                        key: value
                        for key, value in entry_data.items()
                        if key != _RAW_HOST_KEY
                    }
                    if data != current_options or clean_entry_data != dict(self.config_entry.data):
                        self.hass.config_entries.async_update_entry(
                            self.config_entry,
                            data=clean_entry_data,
                            options=data,
                        )
                    else:
                        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    return self.async_abort(reason="rebuild_entity_ids_done")
                clean_entry_data = {
                    key: value
                    for key, value in entry_data.items()
                    if key != _RAW_HOST_KEY
                }
                if clean_entry_data != dict(self.config_entry.data):
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=clean_entry_data,
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
        values = {
            **dict(self.config_entry.data),
            **dict(self.config_entry.options),
            **dict(user_input or {}),
        }
        available_things = self._available_things(values)
        if user_input is not None and self._device_fields:
            selected_things = set(_selected_checkbox_uids(self._device_fields, user_input))
        else:
            selected_things = get_selected_thing_uids(values)
            if selected_things is None and CONF_ENABLED_THINGS not in values:
                selected_things = {uid for uid, _ in available_things}
            elif selected_things is None:
                selected_things = set()

        thing_schema, self._device_fields = _build_thing_checkbox_section_schema(
            available_things,
            selected_things,
        )
        schema: dict[Any, Any] = {
            **thing_schema,
            vol.Optional(
                CONF_REBUILD_ENTITY_IDS,
                default=False,
            ): bool,
            vol.Optional(CONF_HOST, default=values.get(CONF_HOST) or ""): str,
            vol.Optional(
                CONF_USERNAME,
                default=values.get(CONF_USERNAME) or "installer",
            ): str,
            vol.Optional(CONF_PASSWORD, default=values.get(CONF_PASSWORD) or ""): str,
            **_build_option_schema_fields(values),
        }

        return vol.Schema(schema)

    def _build_options_data(self, user_input: Mapping[str, Any]) -> dict[str, Any]:
        """Merge, normalize, and return user-visible options."""
        data = _normalize_options_input(user_input, self.config_entry.options)
        if self._device_fields:
            data[CONF_ENABLED_THINGS] = _selected_checkbox_uids(self._device_fields, user_input)
        elif CONF_ENABLED_THINGS in self.config_entry.options:
            data[CONF_ENABLED_THINGS] = self.config_entry.options[CONF_ENABLED_THINGS]
        return data

    def _available_things(
        self,
        values: Mapping[str, Any] | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return known things for the options form."""
        coordinator = getattr(self.config_entry, "runtime_data", None)
        things = getattr(coordinator, "things", {}) or {}
        selectable_things = SOLARWATTItemsConfigFlow._selectable_things(things)
        if (values or {}).get(CONF_KIWIGRID_HEMS_ENABLED):
            selectable_things.setdefault(
                _KIWIGRID_HEMS_THING_UID,
                _kiwigrid_hems_selection_thing(),
            )
        return SOLARWATTItemsConfigFlow._sorted_things(
            selectable_things
        )
