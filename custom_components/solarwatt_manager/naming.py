from __future__ import annotations

import re
from functools import lru_cache

# -----------------------------
# Name normalization (display + entity_id friendliness)
# -----------------------------
# Current normalization removes technical prefixes entirely.
CONDITIONAL_ID_RULES = [
    r"^kiwigrid_location_standard_([^_]+)_harmonized_",
    r"^pvplant_standard_([^_]+)_", 
    r"^foxesshybrid_battery_([^_]+)_",
    r"^foxesshybrid_inverter_([^_]+)_",
    r"^foxesshybrid_meter_([^_]+)_",
    r"^keba_wallbox_([^_]+)_",    
    r"^mystrom_switch_([^_]+)_",
    r"^modbus_sunspec_sma_inverter_([^_]+)_",
    r"^modbus_sunspec_fronius_inverter_([^_]+)_",
    r"^myreserveethernet_myreserve_([^_]+)_",
    r"^myreserveethernet_acs_([^_]+)_(?:0_)?",
    r"^kgshelly_gen2switch_([^_]+)_(?:0_)?",
    # Strip the BatteryFlex device id and optional group prefix.
    r"^batteryflex_battery_([^_]+)_(?:harmonized_|batteryChannelGroup_)?",
    r"^solarwattBattery_batteryflex_BatteryFlex_([^_]+)_(?:harmonized_|batteryChannelGroup_)?",
    # Drop the variable KACO device segment but keep the functional suffix block.
    r"^sunspecnext_inverter_KACO_.*?_(?=(?:harmonized_|inverter_|limitable_|pv_power_production_))",
]


STATIC_NORMALIZATION_RULES: list[tuple[str, str]] = [
    (r"(^|_)battery_battery_", r"\1battery_"),
]

SPECIAL_DISPLAY_NAMES: dict[str, str] = {
    "gridPower": "Grid Power",
    "batteryPower": "Battery Power",
    "selfConsumedPower": "Self Consumed Power",
    "batteryChargePower": "Battery Charge Power",
    "batteryDischargePower": "Battery Discharge Power",
    "householdFromBatteryPower": "Household From Battery Power",
    "householdFromGridPower": "Household From Grid Power",
    "householdFromPvPower": "Household From PV Power",
    "batterySoc": "Battery SoC",
}


@lru_cache(maxsize=1)
def _compiled_conditional_id_rules() -> list[re.Pattern[str]]:
    return [re.compile(pattern) for pattern in CONDITIONAL_ID_RULES]

@lru_cache(maxsize=1)
def _compiled_static_normalization_rules() -> list[tuple[re.Pattern[str], str]]:
    return [(re.compile(pattern), repl) for pattern, repl in STATIC_NORMALIZATION_RULES]



_HEMS_ITEM_RE = re.compile(
    r"^hems_(?P<kind>battery|pv_plant|evstation|plug|device|flow|analytics_consumption|analytics_production|analytics_storage|analytics_independence|analytics_finance)_"
    r"(?:(?P<id>[0-9a-f]{8}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{12}|v11)_)?"
    r"(?P<suffix>.+)$",
    re.IGNORECASE,
)
_HEMS_ANALYTICS_KINDS = {
    "analytics_consumption",
    "analytics_production",
    "analytics_storage",
    "analytics_independence",
    "analytics_finance",
}


def _hems_item_match(raw: str) -> re.Match[str] | None:
    """Return parsed KiwiGrid HEMS item metadata."""
    return _HEMS_ITEM_RE.match(clean_item_key(raw))


def _is_hems_analytics_kind(kind: str | None) -> bool:
    """Return True for synthetic daily hems analytics items."""
    return bool(kind and kind.lower() in _HEMS_ANALYTICS_KINDS)


def hems_item_kind(raw: str) -> str | None:
    """Return the KiwiGrid HEMS item kind."""
    match = _hems_item_match(raw)
    if not match:
        return None
    return match.group("kind").lower()


def hems_item_suffix(raw: str) -> str | None:
    """Return the functional suffix for a KiwiGrid HEMS item name."""
    match = _hems_item_match(raw)
    if not match:
        return None
    return match.group("suffix")


def is_hems_item_name(raw: str) -> bool:
    """Return True for item names generated from the KiwiGrid HEMS API."""
    return hems_item_suffix(raw) is not None


def hems_entity_object_id(device_name: str, item_name: str) -> str | None:
    """Return a compact object_id for a KiwiGrid HEMS entity.

    The OpenHAB-like item name keeps the KiwiGrid UUID for uniqueness, but the
    Home Assistant entity_id should be user-friendly. For example:
    ``hems_battery_<uuid>_state_of_charge`` on device
    ``SOLARWATT Battery vision three`` becomes
    ``solarwatt_battery_vision_three_state_of_charge``.
    """
    suffix = hems_item_suffix(item_name)
    if not suffix:
        return None

    device_slug = slugify_entity_name(device_name)
    kind = hems_item_kind(item_name)
    suffix_slug = _hems_entity_suffix_slug(
        suffix,
        device_name,
        is_physical=not _is_hems_analytics_kind(kind),
    )

    if not _is_hems_analytics_kind(kind):
        return compose_slug_parts(device_slug, suffix_slug) or None

    return compose_slug_parts(device_slug, suffix_slug) or None


def _hems_entity_suffix_slug(
    suffix: str,
    device_name: str,
    *,
    is_physical: bool,
) -> str:
    """Return the object-id suffix for a HEMS item."""
    normalized_suffix = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", suffix)
    suffix_slug = trim_device_tokens(normalized_suffix, device_name)
    if not is_physical:
        return suffix_slug
    return _strip_leading_slug_token(suffix_slug, "hems")


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
    if hems_suffix := hems_item_suffix(raw):
        base_name = hems_suffix
    else:
        clean_item_name = normalize_item_name(raw)
        if clean_item_name in SPECIAL_DISPLAY_NAMES:
            return SPECIAL_DISPLAY_NAMES[clean_item_name]
        base_name = clean_item_name.replace("harmonized_", "")

    base_name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", base_name)
    base_name = base_name.replace("_", " ").strip()
    return format_display_name(base_name)


def slugify_entity_name(name: str) -> str:
    """Return a Home Assistant friendly object-id fragment."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower())
    slug = re.sub(r"_+", "_", slug)
    return slug.strip("_")


def _slug_tokens(name: str) -> list[str]:
    """Return non-empty slug tokens for display or object-id text."""
    return [token for token in slugify_entity_name(name).split("_") if token]


def _join_slug_tokens(tokens: list[str]) -> str:
    """Join slug tokens into one Home Assistant object-id fragment."""
    return "_".join(token for token in tokens if token)


def _strip_leading_slug_token(slug: str, token: str) -> str:
    """Remove one leading marker token from a slug."""
    tokens = _slug_tokens(slug)
    if tokens[:1] == [token]:
        tokens = tokens[1:]
    return _join_slug_tokens(tokens)


def _move_leading_slug_token_to_end(slug: str, token: str) -> str:
    """Move one leading marker token to the end of a slug."""
    tokens = _slug_tokens(slug)
    if tokens[:1] == [token] and len(tokens) > 1:
        tokens = tokens[1:] + [token]
    return _join_slug_tokens(tokens)


def trim_device_tokens(entity_name: str, device_name: str) -> str:
    """Remove a duplicated device prefix or overlap from an entity/object name."""
    entity_tokens = _slug_tokens(entity_name)
    device_tokens = _slug_tokens(device_name)

    if not entity_tokens or not device_tokens:
        return _join_slug_tokens(entity_tokens)

    if entity_tokens[: len(device_tokens)] == device_tokens:
        entity_tokens = entity_tokens[len(device_tokens):]

    max_overlap = min(len(device_tokens), len(entity_tokens))
    for overlap in range(max_overlap, 0, -1):
        if entity_tokens[:overlap] == device_tokens[-overlap:]:
            entity_tokens = entity_tokens[overlap:]
            break

    return _join_slug_tokens(entity_tokens)


def compose_slug_parts(*parts: str | None) -> str:
    """Return one object-id slug from already-normalized or display-name parts."""
    tokens: list[str] = []
    for part in parts:
        tokens.extend(_slug_tokens(part or ""))
    return _join_slug_tokens(tokens)


def compose_entity_object_id(device_name: str, entity_name: str) -> str:
    """Return a stable object-id from device and entity names without duplicates."""
    clean_device_name = slugify_entity_name(device_name)
    clean_entity_name = trim_device_tokens(entity_name, device_name)
    return compose_slug_parts(clean_device_name, clean_entity_name)


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
