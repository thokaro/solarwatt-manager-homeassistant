from __future__ import annotations

import re
from functools import lru_cache

# -----------------------------
# Name normalization (display + entity_id friendliness)
# -----------------------------
# Add more rules by appending (pattern, replacement).
# Patterns are applied in order.
NORMALIZATION_RULES: list[tuple[str, str]] = [
    # kiwigrid_location_standard_<ID>_harmonized_... -> kiwigrid_...
    (r"^kiwigrid_location_standard_[^_]+_harmonized_", "kiwigrid_"),
    # foxesshybrid_battery_<ID>_... -> foxess_...
    (r"^foxesshybrid_battery_[^_]+_", "foxess_"),
    (r"^foxesshybrid_inverter_[^_]+_", "foxessinv_"),
    (r"^foxesshybrid_meter_[^_]+_", "foxessmeter_"),
    (r"^keba_wallbox_[^_]+_", "keba_"),
    (r"^mystrom_switch_[^_]+_", "mystrom_"),
    (r"^modbus_sunspec_sma_inverter_[^_]+_", "sma_"),
    (r"^pvplant_standard_[^_]+_", "pvplant_"),
]


# -----------------------------
# Default enabled sensors
# -----------------------------
# Add new defaults by adding suffixes below (no need to touch sensor.py).
DEFAULT_ENABLED_GROUPS: list[tuple[str, list[str]]] = [
    (
        r"kiwigrid_location_standard_[^_]+_harmonized_",
        [
            # kiwigrid power (instant)
            "power_in",
            "power_out",
            "power_produced",
            "power_released",
            "power_consumed",
            "power_consumed_from_grid",
            "power_consumed_from_storage",
            "power_consumed_from_producers",
            "power_buffered",
            "power_buffered_from_grid",
            "power_buffered_from_producers",
            "power_self_consumed",
            "power_self_supplied",
            # kiwigrid energy totals (work)
            "work_in_total",
            "work_out_total",
            "work_produced_total",
            "work_released_total",
            "work_consumed_total",
            "work_consumed_from_grid_total",
            "work_consumed_from_storage_total",
            "work_consumed_from_producers_total",
            "work_buffered_total",
            "work_buffered_from_grid_total",
            "work_buffered_from_producers_total",
            "work_self_consumed_total",
            "work_self_supplied_total",
        ],
    ),
    (
        r"foxesshybrid_battery_[^_]+_",
        [
            "battery_bms_power",
            "battery_work_in_total",
            "battery_work_out_total",
            "battery_mode",
            "battery_bms_1_soc",
            "battery_bms_1_voltage",
            "battery_bms_1_current",
            "battery_bms_1_temperature",
        ],
    ),
]

DEFAULT_ENABLED_PATTERNS: list[str] = [
    rf"^{prefix}{suffix}$"
    for prefix, suffixes in DEFAULT_ENABLED_GROUPS
    for suffix in suffixes
]


@lru_cache(maxsize=1)
def _compiled_default_patterns() -> list[re.Pattern[str]]:
    return [re.compile(p) for p in DEFAULT_ENABLED_PATTERNS]


@lru_cache(maxsize=1)
def _compiled_normalization_rules() -> list[tuple[re.Pattern[str], str]]:
    return [(re.compile(pattern), repl) for pattern, repl in NORMALIZATION_RULES]


def clean_item_key(raw: str) -> str:
    """Strip OpenHAB leading '#' used for metadata items."""
    return (raw or "").lstrip("#")


def normalize_item_name(raw: str) -> str:
    """Normalize item names using NORMALIZATION_RULES."""
    name = clean_item_key(raw)
    for pattern, repl in _compiled_normalization_rules():
        name = pattern.sub(repl, name)
    return name


def is_enabled_by_default(item_name: str) -> bool:
    """Return True if raw OpenHAB item name matches DEFAULT_ENABLED_PATTERNS."""
    key = clean_item_key(item_name)
    return any(p.match(key) for p in _compiled_default_patterns())
