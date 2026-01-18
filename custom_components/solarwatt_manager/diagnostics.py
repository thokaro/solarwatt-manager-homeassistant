from __future__ import annotations

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

    sample: dict[str, Any] = {}
    numeric_count = 0
    for k, it in list(items.items())[:50]:
        k_clean = (k or "").lstrip("#")
        v = _num_value(it)
        if v is not None:
            numeric_count += 1
        parsed = getattr(it, "parsed", None)
        sample[k_clean] = {
            "type": getattr(it, "oh_type", None),
            "label": getattr(it, "label", None),
            "parsed_value": getattr(parsed, "value", None),
            "unit": getattr(parsed, "unit", None),
            "timestamp_ms": getattr(parsed, "timestamp_ms", None),
        }

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
        "problem_items": _redact(
            {
                "problem_items_top_20": problem_items[:N],
                "problem_items_total": len(problem_items),
            }
        ),
        "data_sample_first_50": _redact(sample),
    }

    return data
