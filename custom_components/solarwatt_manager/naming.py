from __future__ import annotations

import re
from functools import lru_cache

# -----------------------------
# Name normalization (display + entity_id friendliness)
# -----------------------------
# Add more rules by appending (pattern, replacement).
# Patterns are applied in order.
NORMALIZATION_RULES: list[tuple[str, str]] = [
    # foxesshybrid_battery_<ID>_... -> foxess_...
    (r"^foxesshybrid_battery_[^_]+_", "foxess_"),

    # kiwigrid_location_standard_<ID>_harmonized_... -> kiwigrid_...
    (r"^kiwigrid_location_standard_[^_]+_harmonized_", "kiwigrid_"),
]


def clean_item_key(raw: str) -> str:
    """Strip OpenHAB leading '#' used for metadata items."""
    return (raw or "").lstrip("#")


def normalize_item_name(raw: str) -> str:
    """Normalize item names using NORMALIZATION_RULES."""
    name = clean_item_key(raw)
    for pattern, repl in NORMALIZATION_RULES:
        name = re.sub(pattern, repl, name)
    return name


# -----------------------------
# Default enabled sensors
# -----------------------------
# Add new defaults by adding regex strings below (no need to touch sensor.py).
DEFAULT_ENABLED_PATTERNS: list[str] = [
    # kiwigrid power (instant)
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_in$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_out$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_produced$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_released$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_consumed$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_consumed_from_grid$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_consumed_from_storage$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_consumed_from_producers$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_buffered$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_buffered_from_grid$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_buffered_from_producers$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_self_consumed$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_power_self_supplied$",

    # kiwigrid energy totals (work)
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_in_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_out_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_produced_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_released_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_consumed_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_consumed_from_grid_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_consumed_from_storage_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_consumed_from_producers_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_buffered_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_buffered_from_grid_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_buffered_from_producers_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_self_consumed_total$",
    r"^kiwigrid_location_standard_[^_]+_harmonized_work_self_supplied_total$",

    # foxess
    r"^foxesshybrid_battery_[^_]+_battery_soc$",
    r"^foxesshybrid_battery_[^_]+_battery_bms_power$",
    r"^foxesshybrid_battery_[^_]+_battery_work_in_total$",
    r"^foxesshybrid_battery_[^_]+_battery_work_out_total$",
    r"^foxesshybrid_battery_[^_]+_battery_mode$",
    r"^foxesshybrid_battery_[^_]+_battery_bms_1_voltage$",
    r"^foxesshybrid_battery_[^_]+_battery_bms_1_current$",
    r"^foxesshybrid_battery_[^_]+_battery_bms_1_temperature$",
]


@lru_cache(maxsize=1)
def _compiled_default_patterns() -> list[re.Pattern[str]]:
    return [re.compile(p) for p in DEFAULT_ENABLED_PATTERNS]


def is_enabled_by_default(item_name: str) -> bool:
    """Return True if raw OpenHAB item name matches DEFAULT_ENABLED_PATTERNS."""
    key = clean_item_key(item_name)
    return any(p.match(key) for p in _compiled_default_patterns())
