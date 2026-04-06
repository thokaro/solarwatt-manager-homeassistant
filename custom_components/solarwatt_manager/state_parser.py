from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
import unicodedata

_NUM_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([^\d\s].*)?\s*$")
_PATTERN_UNIT_RE = re.compile(r"%[-+0-9.]*[a-zA-Z]")
_UNIT_ALIASES = {
    "A·h": "Ah",
    "kW·h": "kWh",
    "W·h": "Wh",
    "Ohm": "Ω",
    "mOhm": "mΩ",
}
_UNAVAILABLE_STATES = {"NULL", "UNDEF", "UNINITIALIZED"}
_SCALED_UNITS = {
    "mA": (1_000.0, "A"),
    "mV": (1_000.0, "V"),
    "mW": (1_000.0, "W"),
    "mWh": (1_000.0, "Wh"),
    "mHz": (1_000.0, "Hz"),
    "mΩ": (1_000.0, "Ω"),
    "uA": (1_000_000.0, "A"),
    "uV": (1_000_000.0, "V"),
    "uW": (1_000_000.0, "W"),
    "uWh": (1_000_000.0, "Wh"),
    "uHz": (1_000_000.0, "Hz"),
}
_ROUND_DIGITS_BY_UNIT = {
    "kWh": 3,
    "kW": 3,
    "W": 2,
    "V": 2,
    "A": 2,
    "Hz": 2,
    "%": 2,
    "°C": 2,
}


@dataclass
class ParsedState:
    value: Any
    unit: str | None = None
    timestamp_ms: int | None = None


@dataclass
class SOLARWATTItem:
    name: str
    raw: dict[str, Any]
    parsed: ParsedState
    oh_type: str | None
    editable: bool
    label: str | None = None
    category: str | None = None


def _extract_unit_from_pattern(pattern: str | None) -> str | None:
    if not pattern:
        return None
    if "%unit%" in pattern:
        return None
    cleaned = _PATTERN_UNIT_RE.sub("", pattern).strip()
    if not cleaned:
        return None
    parts = cleaned.split()
    return parts[-1] if parts else None


def _normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    unit = unicodedata.normalize("NFKC", unit).strip()
    unit = unit.replace("·", "")
    unit = unit.replace("µ", "u").replace("μ", "u")
    unit = unit.replace("\\u00b0", "°")
    unit = _UNIT_ALIASES.get(unit, unit)
    return unit or None


def _convert_scaled_unit(value: float, unit: str | None) -> tuple[float, str | None]:
    if unit is None:
        return value, None
    if scaled_unit := _SCALED_UNITS.get(unit):
        divisor, target_unit = scaled_unit
        return value / divisor, target_unit
    return value, unit


def _normalize_numeric_state(value: float, unit: str | None) -> tuple[int | float, str | None]:
    if unit == "Ws":
        value /= 3600.0
        unit = "Wh"
    if unit == "Wh":
        value /= 1000.0
        unit = "kWh"
    if unit == "C":
        unit = "°C"

    if (digits := _ROUND_DIGITS_BY_UNIT.get(unit or "")) is not None:
        value = round(value, digits)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return value, unit


def parse_state(
    state: Any,
    pattern: str | None = None,
    oh_type: str | None = None,
) -> ParsedState:
    """Parse an OpenHAB/SOLARWATT state into a typed value and normalized unit."""
    if state is None:
        return ParsedState(value=None)

    s = unicodedata.normalize("NFKC", str(state).strip())

    if s in _UNAVAILABLE_STATES:
        return ParsedState(value=None)

    # Only coerce ON/OFF to bool for switch-like items. For String items
    # such as battery_mode, keep the textual state.
    if s in ("ON", "OFF") and (oh_type or "").startswith("Switch"):
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
        ps = parse_state(right, pattern, oh_type)
        ps.timestamp_ms = ts
        return ps

    # numeric + optional unit
    m = _NUM_RE.match(s)
    if m:
        num_s = m.group(1)
        unit = (m.group(2) or "").strip() or None
        if unit is None:
            unit = _extract_unit_from_pattern(pattern)
        unit = _normalize_unit(unit)
        try:
            val = float(num_s)

            # SOLARWATT/OpenHAB liefert teils Ws, Wh, kWh, kW, °C, etc.
            if unit:
                val, unit = _convert_scaled_unit(val, unit)
            val, unit = _normalize_numeric_state(val, unit)

            return ParsedState(value=val, unit=unit)
        except ValueError:
            pass

    return ParsedState(value=s)
