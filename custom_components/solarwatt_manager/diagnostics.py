from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_ENERGY_DELTA_KWH, DEFAULT_ENERGY_DELTA_KWH, DOMAIN, SOLARWATTConfigEntry


def _redact(obj: Any) -> Any:
    """Redact secrets from diagnostics output."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(s in lk for s in ("password", "token", "cookie", "authorization", "session")):
                out[k] = "REDACTED"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def _item_payload(item: Any) -> dict[str, Any]:
    """Build a compact diagnostics payload for a SOLARWATTItem."""
    parsed = getattr(item, "parsed", None)
    raw = getattr(item, "raw", None)
    pattern = None
    if isinstance(raw, dict):
        pattern = (raw.get("stateDescription") or {}).get("pattern")
    return {
        "type": getattr(item, "oh_type", None),
        "label": getattr(item, "label", None),
        "category": getattr(item, "category", None),
        "editable": getattr(item, "editable", None),
        "raw_state": raw.get("state") if isinstance(raw, dict) else None,
        "state_pattern": pattern,
        "parsed_value": getattr(parsed, "value", None),
        "unit": getattr(parsed, "unit", None),
        "timestamp_ms": getattr(parsed, "timestamp_ms", None),
    }


def _editable_count_key(editable: Any) -> str:
    """Return the diagnostics bucket name for one editable flag."""
    if editable is True:
        return "true"
    if editable is False:
        return "false"
    return "unknown"


def _problem_item_issue(item_name: str, payload: dict[str, Any]) -> str | None:
    """Return the most relevant diagnostics issue for one item payload."""
    value = payload.get("parsed_value")
    if value is None:
        return "value is NULL"
    if not isinstance(value, (int, float)):
        return f"non-numeric value: {value!r}"
    unit = payload.get("unit")
    if unit in (None, "", "N") and any(token in item_name for token in ("power", "work", "energy")):
        return "missing unit"
    return None


def _energy_sensor_write(state) -> dict[str, Any] | None:
    """Return the diagnostics snapshot for one energy sensor state."""
    attrs = state.attributes or {}
    device_class = attrs.get("device_class")
    state_class = attrs.get("state_class")
    if device_class != "energy" and state_class not in ("total", "total_increasing"):
        return None
    return {
        "name": state.name,
        "device_class": device_class,
        "state_class": state_class,
        "unit": attrs.get("unit_of_measurement"),
        "last_updated": state.last_updated.isoformat() if state.last_updated else None,
        "last_changed": state.last_changed.isoformat() if state.last_changed else None,
    }


def _collect_item_diagnostics(items: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Collect compact item payloads, aggregate stats, and problem candidates."""
    item_payloads: dict[str, Any] = {}
    type_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    unit_counts: Counter[str] = Counter()
    editable_counts: Counter[str] = Counter()
    problem_items: list[dict[str, Any]] = []
    numeric_count = 0
    missing_label_count = 0
    null_value_count = 0
    non_numeric_count = 0

    for item_name, item in items.items():
        clean_name = (item_name or "").lstrip("#")
        payload = _item_payload(item)
        value = payload.get("parsed_value")
        item_payloads[clean_name] = payload

        if isinstance(value, (int, float)):
            numeric_count += 1
        elif value is None:
            null_value_count += 1
        else:
            non_numeric_count += 1

        type_counts[payload.get("type") or "unknown"] += 1
        category_counts[payload.get("category") or "unknown"] += 1
        unit_counts[payload.get("unit") or "none"] += 1
        editable_counts[_editable_count_key(payload.get("editable"))] += 1

        if not payload.get("label"):
            missing_label_count += 1
        if issue := _problem_item_issue(clean_name, payload):
            problem_items.append({"name": clean_name, "issue": issue})

    return (
        item_payloads,
        {
            "numeric_items": numeric_count,
            "types": dict(type_counts),
            "categories": dict(category_counts),
            "units": dict(unit_counts),
            "editable": dict(editable_counts),
            "missing_label": missing_label_count,
            "null_value": null_value_count,
            "non_numeric_value": non_numeric_count,
        },
        problem_items,
    )


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    No additional network calls are performed. This is a snapshot of the latest coordinator data.
    """
    coordinator = entry.runtime_data
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    host = getattr(getattr(coordinator, "client", None), "host", None) or entry.entry_id
    dev = dev_reg.async_get_device(identifiers={(DOMAIN, host)})
    device = (
        {
            "name": dev.name,
            "manufacturer": dev.manufacturer,
            "model": dev.model,
            "sw_version": dev.sw_version,
            "hw_version": dev.hw_version,
        }
        if dev
        else None
    )

    items = coordinator.data or {}
    interval = getattr(coordinator, "update_interval", None)
    update_interval_seconds = int(interval.total_seconds()) if interval else None
    energy_delta_kwh = entry.options.get(CONF_ENERGY_DELTA_KWH, DEFAULT_ENERGY_DELTA_KWH)

    energy_sensor_writes = {
        registry_entry.entity_id: sensor_write
        for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if (state := hass.states.get(registry_entry.entity_id)) is not None
        if (sensor_write := _energy_sensor_write(state)) is not None
    }
    item_payloads, item_stats, problem_items = _collect_item_diagnostics(items)

    things = getattr(coordinator, "things", None) or {}
    things_compact: dict[str, Any] = {}
    for uid, thing in things.items():
        status_info = thing.get("statusInfo")
        if not isinstance(status_info, dict):
            status_info = {}
        things_compact[uid] = {
            "label": thing.get("label"),
            "thing_type_uid": thing.get("thingTypeUID") or thing.get("thingTypeUid"),
            "bridge_uid": thing.get("bridgeUID") or thing.get("bridgeUid"),
            "status": status_info.get("status"),
            "status_detail": status_info.get("statusDetail"),
            "properties": thing.get("properties"),
            "channels_count": len(thing.get("channels") or []),
        }

    data: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "domain": entry.domain,
            "data": _redact(dict(entry.data)),
            "options": _redact(dict(entry.options)),
        },
        "device": device,
        "coordinator": {
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "update_interval_seconds": update_interval_seconds,
            "data_items": len(items),
            "numeric_items": item_stats["numeric_items"],
            "last_exception": repr(getattr(coordinator, "last_exception", None)) if getattr(coordinator, "last_exception", None) else None,
        },
        "energy_settings": {
            "energy_delta_kwh": energy_delta_kwh,
            "energy_sensors_last_write": _redact(energy_sensor_writes),
        },
        "data_stats": _redact({key: value for key, value in item_stats.items() if key != "numeric_items"}),
        "data_items_compact": _redact(item_payloads),
        "problem_items": _redact(
            {
                "problem_items_top_20": problem_items[:20],
                "problem_items_total": len(problem_items),
            }
        ),
        "things": _redact(
            {
                "things_count": len(things_compact),
                "things_compact": things_compact,
            }
        ),
    }

    return data
