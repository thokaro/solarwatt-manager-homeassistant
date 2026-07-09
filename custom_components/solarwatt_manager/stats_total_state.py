from __future__ import annotations

import math
from typing import Any


class StatsTotalState:
    """Track year-to-total rollover state and offsets."""

    def __init__(
        self,
        sources: dict[str, dict[str, float]] | None = None,
        offsets: dict[str, float] | None = None,
    ) -> None:
        self.sources = sources or {}
        self.offsets = offsets or {}
        self.dirty = False

    def calculated_value(self, source_key: str, year_value: Any) -> float | None:
        current = finite_float(year_value)
        if current is None:
            return None

        source = self.sources.setdefault(source_key, {})
        previous = finite_float(source.get("last"))
        base = finite_float(source.get("base")) or 0.0

        if previous is not None and current < previous:
            base += previous
            source["base"] = base

        if previous != current:
            source["last"] = current
            self.dirty = True

        return base + current

    def value_with_offset(self, source_key: str, year_value: Any) -> float | None:
        calculated = self.calculated_value(source_key, year_value)
        if calculated is None:
            return None
        return calculated + self.offset(source_key)

    def offset(self, source_key: str) -> float:
        return finite_float(self.offsets.get(source_key)) or 0.0

    def set_offset(self, source_key: str, offset: Any) -> None:
        value = finite_float(offset)
        if value is None:
            raise ValueError("Offset must be a finite number")
        self.offsets[source_key] = value
        self.dirty = True

    def set_desired_value(self, source_key: str, desired_value: Any, year_value: Any) -> float:
        desired = finite_float(desired_value)
        if desired is None:
            raise ValueError("Desired value must be a finite number")
        calculated = self.calculated_value(source_key, year_value)
        if calculated is None:
            raise ValueError("Current calculated value is not available")
        offset = desired - calculated
        self.set_offset(source_key, offset)
        return offset

    def reset_offset(self, source_key: str) -> None:
        if source_key in self.offsets:
            del self.offsets[source_key]
            self.dirty = True


def finite_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def float_records(value: Any) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        return {}

    records: dict[str, dict[str, float]] = {}
    for key, record in value.items():
        if not isinstance(record, dict):
            continue
        parsed: dict[str, float] = {}
        for record_key in ("base", "last"):
            if (record_value := finite_float(record.get(record_key))) is not None:
                parsed[record_key] = record_value
        if parsed:
            records[str(key)] = parsed
    return records


def float_values(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): parsed
        for key, raw in value.items()
        if (parsed := finite_float(raw)) is not None
    }
