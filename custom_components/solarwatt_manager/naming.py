from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from functools import lru_cache

# -----------------------------
# Name normalization (display + entity_id friendliness)
# -----------------------------
# Add more conditional rules by appending
# (device_type, pattern, single-device replacement, multi-device replacement).
# Patterns are applied in order.
CONDITIONAL_ID_RULES: list[tuple[str, str, str, str]] = [
    # kiwigrid_location_standard_<ID>_harmonized_... -> kiwigrid_...
    ("kiwigrid", r"^kiwigrid_location_standard_([^_]+)_harmonized_", "kiwigrid_", r"kiwigrid_\1_"),
    # foxesshybrid_battery_<ID>_... -> foxess_...
    ("foxess", r"^foxesshybrid_battery_([^_]+)_", "foxess_", r"foxess_\1_"),
    ("foxessinv", r"^foxesshybrid_inverter_([^_]+)_", "foxessinv_", r"foxessinv_\1_"),
    ("foxessmeter", r"^foxesshybrid_meter_([^_]+)_", "foxessmeter_", r"foxessmeter_\1_"),
    ("keba", r"^keba_wallbox_([^_]+)_", "keba_", r"keba_\1_"),
    ("mystrom", r"^mystrom_switch_([^_]+)_", "mystrom_", r"mystrom_\1_"),
    ("sma", r"^modbus_sunspec_sma_inverter_([^_]+)_", "sma_", r"sma_\1_"),
    ("fronius", r"^modbus_sunspec_fronius_inverter_([^_]+)_", "fronius_", r"fronius_\1_"),
    ("myreserve", r"^myreserveethernet_myreserve_([^_]+)_", "myreserve_", r"myreserve_\1_"),
    ("acs", r"^myreserveethernet_acs_([^_]+)_0_", "acs_", r"acs_\1_"),
    ("acs", r"^myreserveethernet_acs_([^_]+)_", "acs_", r"acs_\1_"),
    ("pvplant", r"^pvplant_standard_([^_]+)_", "pvplant_", r"pvplant_\1_"),
    ("batteryflex", r"^batteryflex_battery_([^_]+)_harmonized_", "batteryflex_", r"batteryflex_\1_"),
    ("batteryflex", r"^batteryflex_battery_([^_]+)_batteryChannelGroup_", "batteryflex_", r"batteryflex_\1_"),
    ("batteryflex", r"^batteryflex_battery_([^_]+)_", "batteryflex_", r"batteryflex_\1_"),
    ("batteryflex", r"^solarwattBattery_batteryflex_BatteryFlex_([^_]+)_harmonized_", "batteryflex_", r"batteryflex_\1_"),
    ("batteryflex", r"^solarwattBattery_batteryflex_BatteryFlex_([^_]+)_batteryChannelGroup_", "batteryflex_", r"batteryflex_\1_"),
    ("batteryflex", r"^solarwattBattery_batteryflex_BatteryFlex_([^_]+)_", "batteryflex_", r"batteryflex_\1_"),
    # Shorten KACO device block while preserving known suffix groups.
    (
        "kacoinv",
        r"^sunspecnext_inverter_KACO_(.*?)_(?=(harmonized_|inverter_|limitable_|pv_power_production_))",
        "kacoinv_",
        r"kacoinv_\1_",
    ),
]


STATIC_NORMALIZATION_RULES: list[tuple[str, str]] = []


@lru_cache(maxsize=1)
def _compiled_conditional_id_rules() -> list[tuple[str, re.Pattern[str], str, str]]:
    return [
        (device_type, re.compile(pattern), single_repl, multi_repl)
        for device_type, pattern, single_repl, multi_repl in CONDITIONAL_ID_RULES
    ]


@lru_cache(maxsize=1)
def _compiled_static_normalization_rules() -> list[tuple[re.Pattern[str], str]]:
    return [(re.compile(pattern), repl) for pattern, repl in STATIC_NORMALIZATION_RULES]


def clean_item_key(raw: str) -> str:
    """Strip OpenHAB leading '#' used for metadata items."""
    return (raw or "").lstrip("#")


def detect_multi_instance_device_types(item_names: Iterable[str] | None) -> set[str]:
    """Return device types whose item names contain multiple distinct device IDs."""
    if not item_names:
        return set()

    device_ids_by_type: dict[str, set[str]] = {}
    for item_name in item_names:
        name = clean_item_key(item_name)
        for device_type, pattern, _single_repl, _multi_repl in _compiled_conditional_id_rules():
            match = pattern.match(name)
            if not match:
                continue
            device_ids_by_type.setdefault(device_type, set()).add(match.group(1))
            break

    return {
        device_type
        for device_type, device_ids in device_ids_by_type.items()
        if len(device_ids) > 1
    }


def _normalize_static_item_name(name: str) -> str:
    for pattern, repl in _compiled_static_normalization_rules():
        name = pattern.sub(repl, name)
    return name


def normalize_item_name(
    raw: str,
    multi_instance_device_types: Collection[str] | None = None,
) -> str:
    """Normalize item names using conditional and static normalization rules."""
    name = clean_item_key(raw)
    multi_instance_device_types = set(multi_instance_device_types or ())

    for device_type, pattern, single_repl, multi_repl in _compiled_conditional_id_rules():
        repl = multi_repl if device_type in multi_instance_device_types else single_repl
        name = pattern.sub(repl, name)

    return _normalize_static_item_name(name)


def normalized_item_name_variants(raw: str) -> set[str]:
    """Return all legacy normalized variants for an item name."""
    name = clean_item_key(raw)
    variants = {name}

    for _device_type, pattern, single_repl, multi_repl in _compiled_conditional_id_rules():
        if not pattern.match(name):
            continue
        variants = {
            pattern.sub(repl, variant)
            for variant in variants
            for repl in (single_repl, multi_repl)
        }
        break

    return {_normalize_static_item_name(variant) for variant in variants}


def format_display_name(name: str) -> str:
    """Format a human-friendly display name (Title Case with exceptions)."""
    if not name:
        return name

    def _format_token(token: str) -> str:
        if not token:
            return token
        if token.isdigit():
            return token

        lower = token.lower()
        for key, replacement in (
            ("bms", "BMS"),
            ("soc", "SoC"),
            ("soh", "SoH"),
            ("ac", "AC"),
            ("dc", "DC"),
            ("pv", "PV"),
            ("mppt", "MPPT"),
            ("acs", "ACS"),
            ("sma", "SMA"),
            ("fronius", "Fronius"),
            ("keba", "KEBA"),
            ("sunspec", "SunSpec"),
            ("inv", "INV"),
            ("modbus", "Modbus"),
            ("foxess", "FoxESS"),
            ("foxessinv", "FoxESSInv"),
            ("mystrom", "myStrom"),
        ):
            if lower == key or (lower.startswith(key) and lower[len(key):].isdigit()):
                return replacement + token[len(key):]

        if token != token.lower():
            return token

        return token.capitalize()

    parts = re.split(r"([^A-Za-z0-9]+)", name)
    return "".join(_format_token(part) if idx % 2 == 0 else part for idx, part in enumerate(parts))
