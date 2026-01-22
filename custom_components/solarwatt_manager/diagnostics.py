from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


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


def _num_value(item: Any) -> float | None:
    """Extract a numeric value from a SOLARWATTItem or similar wrapper."""
    if item is None:
        return None
    if hasattr(item, "parsed"):
        val = getattr(getattr(item, "parsed", None), "value", None)
    else:
        val = getattr(item, "value", None)
    if isinstance(val, (int, float)):
        return float(val)
    return None


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
        "group_names": getattr(item, "group_names", None),
        "raw_state": raw.get("state") if isinstance(raw, dict) else None,
        "state_pattern": pattern,
        "parsed_value": getattr(parsed, "value", None),
        "unit": getattr(parsed, "unit", None),
        "timestamp_ms": getattr(parsed, "timestamp_ms", None),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    No additional network calls are performed. This is a snapshot of the latest coordinator data.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]
    dev_reg = dr.async_get(hass)

    device = None
    host = getattr(getattr(coordinator, "client", None), "host", None) or entry.entry_id
    dev = dev_reg.async_get_device(identifiers={(DOMAIN, host)})
    if dev:
        device = {
            "name": dev.name,
            "manufacturer": dev.manufacturer,
            "model": dev.model,
            "sw_version": dev.sw_version,
            "hw_version": dev.hw_version,
        }

    items = coordinator.data or {}

    interval = getattr(coordinator, "update_interval", None)
    update_interval_seconds = int(interval.total_seconds()) if interval else None

    item_payloads: dict[str, Any] = {}
    item_keys: list[str] = []
    numeric_count = 0
    type_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    unit_counts: Counter[str] = Counter()
    editable_counts: Counter[str] = Counter()
    missing_label_count = 0
    null_value_count = 0
    non_numeric_count = 0

    for k, it in items.items():
        k_clean = (k or "").lstrip("#")
        payload = _item_payload(it)
        item_payloads[k_clean] = payload
        item_keys.append(k_clean)

        if _num_value(it) is not None:
            numeric_count += 1

        type_counts[payload.get("type") or "unknown"] += 1
        category_counts[payload.get("category") or "unknown"] += 1
        unit_counts[payload.get("unit") or "none"] += 1

        editable = payload.get("editable")
        if editable is True:
            editable_counts["true"] += 1
        elif editable is False:
            editable_counts["false"] += 1
        else:
            editable_counts["unknown"] += 1

        if not payload.get("label"):
            missing_label_count += 1

        val = payload.get("parsed_value")
        if val is None:
            null_value_count += 1
        elif not isinstance(val, (int, float)):
            non_numeric_count += 1

    item_pairs = list(item_payloads.items())
    sample = dict(item_pairs[:50])
    sample_tail = dict(item_pairs[-50:]) if len(item_pairs) > 50 else {}

    # Highlight the most common problems to speed up support.
    N = 20
    problem_items: list[dict[str, Any]] = []
    for k, it in items.items():
        k_clean = (k or "").lstrip("#")
        parsed = getattr(it, "parsed", None)
        val = getattr(parsed, "value", None) if parsed is not None else getattr(it, "value", None)
        unit = getattr(parsed, "unit", None) if parsed is not None else None

        if val is None:
            problem_items.append({"name": k_clean, "issue": "value is NULL"})
            continue

        if not isinstance(val, (int, float)):
            problem_items.append({"name": k_clean, "issue": f"non-numeric value: {repr(val)}"})
            continue

        if unit in (None, "", "N") and any(tok in k_clean for tok in ("power", "work", "energy")):
            problem_items.append({"name": k_clean, "issue": "missing unit"})
            continue

    things = getattr(coordinator, "things", None) or {}
    things_compact: dict[str, Any] = {}
    for uid, thing in things.items():
        status_info = thing.get("statusInfo") or {}
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
            "numeric_items": numeric_count,
            "last_exception": repr(getattr(coordinator, "last_exception", None)) if getattr(coordinator, "last_exception", None) else None,
        },
        "data_keys": item_keys,
        "data_stats": _redact(
            {
                "types": dict(type_counts),
                "categories": dict(category_counts),
                "units": dict(unit_counts),
                "editable": dict(editable_counts),
                "missing_label": missing_label_count,
                "null_value": null_value_count,
                "non_numeric_value": non_numeric_count,
            }
        ),
        "data_items_compact": _redact(item_payloads),
        "problem_items": _redact(
            {
                "problem_items_top_20": problem_items[:N],
                "problem_items_total": len(problem_items),
            }
        ),
        "data_sample_first_50": _redact(sample),
        "data_sample_last_50": _redact(sample_tail) if sample_tail else None,
        "things": _redact(
            {
                "things_count": len(things_compact),
                "things_compact": things_compact,
            }
        ),
    }

    return data
