from __future__ import annotations

import re
from functools import lru_cache

# -----------------------------
# Name normalization (display + entity_id friendliness)
# -----------------------------
# Current normalization removes technical prefixes entirely.
CONDITIONAL_ID_RULES = [
    r"^kiwigrid_location_standard_([^_]+)_harmonized_",
    r"^foxesshybrid_battery_([^_]+)_",
    r"^foxesshybrid_inverter_([^_]+)_",
    r"^foxesshybrid_meter_([^_]+)_",
    r"^keba_wallbox_([^_]+)_",
    r"^mystrom_switch_([^_]+)_",
    r"^modbus_sunspec_sma_inverter_([^_]+)_",
    r"^modbus_sunspec_fronius_inverter_([^_]+)_",
    r"^myreserveethernet_myreserve_([^_]+)_",
    r"^myreserveethernet_acs_([^_]+)_0_",
    r"^myreserveethernet_acs_([^_]+)_",
    r"^pvplant_standard_([^_]+)_",
    r"^batteryflex_battery_([^_]+)_harmonized_",
    r"^batteryflex_battery_([^_]+)_batteryChannelGroup_",
    r"^batteryflex_battery_([^_]+)_",
    r"^solarwattBattery_batteryflex_BatteryFlex_([^_]+)_harmonized_",
    r"^solarwattBattery_batteryflex_BatteryFlex_([^_]+)_batteryChannelGroup_",
    r"^solarwattBattery_batteryflex_BatteryFlex_([^_]+)_",
    r"^sunspecnext_inverter_KACO_(.*?)_(?=(harmonized_|inverter_|limitable_|pv_power_production_))",
]


STATIC_NORMALIZATION_RULES: list[tuple[str, str]] = [
    (r"(^|_)battery_battery_", r"\1battery_"),
]


@lru_cache(maxsize=1)
def _compiled_conditional_id_rules() -> list[re.Pattern[str]]:
    return [re.compile(pattern) for pattern in CONDITIONAL_ID_RULES]


@lru_cache(maxsize=1)
def _compiled_static_normalization_rules() -> list[tuple[re.Pattern[str], str]]:
    return [(re.compile(pattern), repl) for pattern, repl in STATIC_NORMALIZATION_RULES]


def clean_item_key(raw: str) -> str:
    """Strip OpenHAB leading '#' used for metadata items."""
    return (raw or "").lstrip("#")


def _normalize_static_item_name(name: str) -> str:
    for pattern, repl in _compiled_static_normalization_rules():
        name = pattern.sub(repl, name)
    return name


def normalize_item_name(
    raw: str,
) -> str:
    """Normalize item names using conditional and static normalization rules."""
    name = clean_item_key(raw)

    for pattern in _compiled_conditional_id_rules():
        name = pattern.sub("", name)

    return _normalize_static_item_name(name)


def item_entity_name(
    raw: str,
) -> str:
    """Return the user-facing entity name derived from one raw item key."""
    clean_item_name = normalize_item_name(raw)
    base_name = clean_item_name.replace("harmonized_", "").replace("_", " ").strip()
    return format_display_name(base_name)


def slugify_entity_name(name: str) -> str:
    """Return a Home Assistant friendly object-id fragment."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower())
    slug = re.sub(r"_+", "_", slug)
    return slug.strip("_")


def trim_device_tokens(entity_name: str, device_name: str) -> str:
    """Remove a duplicated device prefix or overlap from an entity/object name."""
    entity_tokens = [token for token in slugify_entity_name(entity_name).split("_") if token]
    device_tokens = [token for token in slugify_entity_name(device_name).split("_") if token]

    if not entity_tokens or not device_tokens:
        return "_".join(entity_tokens)

    if entity_tokens[: len(device_tokens)] == device_tokens:
        entity_tokens = entity_tokens[len(device_tokens):]

    max_overlap = min(len(device_tokens), len(entity_tokens))
    for overlap in range(max_overlap, 0, -1):
        if entity_tokens[:overlap] == device_tokens[-overlap:]:
            entity_tokens = entity_tokens[overlap:]
            break

    return "_".join(entity_tokens)


def compose_entity_object_id(device_name: str, entity_name: str) -> str:
    """Return a stable object-id from device and entity names without duplicates."""
    clean_device_name = slugify_entity_name(device_name)
    clean_entity_name = trim_device_tokens(entity_name, device_name)

    if not clean_device_name:
        return clean_entity_name
    if not clean_entity_name:
        return clean_device_name

    return f"{clean_device_name}_{clean_entity_name}"


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
