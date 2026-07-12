from __future__ import annotations

from collections.abc import Callable, Mapping
import re
from typing import Any


ThingPredicate = Callable[[Mapping[str, Any]], bool]
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_DETAIL_TOKENS = (
    "battery",
    "ev_station",
    "inverter",
    "kecontact",
    "manager",
    "meter",
    "plug",
    "pv",
    "solarwatt",
    "switch",
    "wallbox",
    "wechselrichter",
)
_TYPE_TOKENS = {
    "battery": ("battery",),
    "evstation": ("ev_station", "evstation", "wallbox", "keba", "kecontact"),
    "inverter": ("inverter", "wechselrichter"),
    "meter": ("meter", "zaehler", "zähler"),
    "plug": ("plug", "mystrom", "switch", "steckdose"),
    "pv": ("pv", "photovoltaic"),
    "energy_manager": ("energy_manager", "manager"),
}


def canonicalize_thing_key(value: Any) -> str:
    """Return a normalized key used to match thing metadata."""
    return _NON_ALNUM_RE.sub("_", str(value or "").strip().lower()).strip("_")


def is_kiwigrid_hems_thing(thing: Mapping[str, Any]) -> bool:
    """Return whether a thing contains KiwiGrid HEMS metadata."""
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    return bool(str(props.get("kiwigridKind") or props.get("kiwigridEndpoint") or "").strip())


def is_local_bridge_thing(thing: Mapping[str, Any]) -> bool:
    """Return whether a thing is a local HEMS bridge/container."""
    thing_type_uid = str(thing.get("thingTypeUID") or thing.get("thingTypeUid") or "").lower()
    return ":bridge" in thing_type_uid or thing_type_uid.endswith(":bridge")


def resolve_thing_uid(
    existing_things: Mapping[str, dict[str, Any]],
    incoming: Mapping[str, Any],
    fallback_uid: str,
    *,
    is_hems_thing: ThingPredicate = is_kiwigrid_hems_thing,
    is_bridge_thing: ThingPredicate = is_local_bridge_thing,
) -> str:
    """Return an existing UID for a matching incoming thing."""
    if is_bridge_thing(incoming):
        return fallback_uid

    incoming_serial = _thing_serial_key(incoming)
    incoming_label = _thing_label_key(incoming)
    incoming_name = _thing_name_key(incoming)
    incoming_type = _thing_type_key(incoming)
    if not incoming_serial and not incoming_label and not incoming_name:
        return fallback_uid

    for existing_uid, existing in existing_things.items():
        if (
            not isinstance(existing, Mapping)
            or is_hems_thing(existing)
            or is_bridge_thing(existing)
        ):
            continue

        existing_serial = _thing_serial_key(existing)
        if incoming_serial and existing_serial and incoming_serial == existing_serial:
            return existing_uid
        if incoming_serial and existing_serial and incoming_serial != existing_serial:
            continue

        existing_label = _thing_label_key(existing)
        if incoming_label and existing_label and incoming_label == existing_label:
            return existing_uid

        existing_name = _thing_name_key(existing)
        if (
            incoming_name
            and existing_name
            and incoming_name == existing_name
            and (not incoming_type or not (existing_type := _thing_type_key(existing)) or incoming_type == existing_type)
        ):
            return existing_uid

    return fallback_uid


def merge_selection_things(
    base_things: Mapping[str, dict[str, Any]],
    incoming_things: Mapping[str, dict[str, Any]],
    *,
    is_hems_thing: ThingPredicate = is_kiwigrid_hems_thing,
    is_bridge_thing: ThingPredicate = is_local_bridge_thing,
) -> dict[str, dict[str, Any]]:
    """Merge things into one device-selection record per physical device."""
    merged: dict[str, dict[str, Any]] = dict(base_things)
    for raw_uid, incoming in incoming_things.items():
        uid = resolve_thing_uid(
            merged,
            incoming,
            raw_uid,
            is_hems_thing=is_hems_thing,
            is_bridge_thing=is_bridge_thing,
        )
        thing = incoming
        if uid != raw_uid:
            thing = dict(thing)
            thing["UID"] = uid
            thing["uid"] = uid
        if uid in merged:
            thing = _merge_selection_records(merged[uid], thing)
        merged[uid] = thing
    return merged


def merge_thing_records(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge local and KiwiGrid records belonging to the same physical device."""
    merged = dict(existing)
    existing_label = str(existing.get("label") or "").strip()
    incoming_label = str(incoming.get("label") or "").strip()
    existing_uid = str(existing.get("UID") or existing.get("uid") or "")
    if incoming_label and (not existing_label or existing_label == existing_uid):
        merged["label"] = incoming_label

    merged["properties"] = _merged_properties(existing, incoming)
    merged["channels"] = _merge_channels(existing, incoming, copy_incoming=False)

    existing_status = (
        existing.get("statusInfo") if isinstance(existing.get("statusInfo"), dict) else {}
    )
    incoming_status = (
        incoming.get("statusInfo") if isinstance(incoming.get("statusInfo"), dict) else {}
    )
    if str(existing_status.get("status") or "").upper() in {"", "UNKNOWN", "OFFLINE"}:
        merged["statusInfo"] = {**existing_status, **incoming_status}
    return merged


def _merge_selection_records(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(existing)
    merged["properties"] = _merged_properties(existing, incoming)
    merged["channels"] = _merge_channels(existing, incoming, copy_incoming=True)
    return merged


def _merged_properties(
    existing: Mapping[str, Any], incoming: Mapping[str, Any]
) -> dict[str, Any]:
    existing_props = existing.get("properties")
    incoming_props = incoming.get("properties")
    return {
        **(existing_props if isinstance(existing_props, dict) else {}),
        **(incoming_props if isinstance(incoming_props, dict) else {}),
    }


def _merge_channels(
    existing: Mapping[str, Any],
    incoming: Mapping[str, Any],
    *,
    copy_incoming: bool,
) -> list[Any]:
    existing_channels = existing.get("channels")
    incoming_channels = incoming.get("channels")
    channels = list(existing_channels) if isinstance(existing_channels, list) else []
    seen = {
        str(channel.get("uid") or channel.get("id") or "")
        for channel in channels
        if isinstance(channel, Mapping)
    }
    for channel in incoming_channels if isinstance(incoming_channels, list) else []:
        if not isinstance(channel, Mapping):
            continue
        key = str(channel.get("uid") or channel.get("id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        channels.append(dict(channel) if copy_incoming else channel)
    return channels


def _thing_label_key(thing: Mapping[str, Any]) -> str:
    return canonicalize_thing_key(thing.get("label"))


def _thing_name_key(thing: Mapping[str, Any]) -> str:
    label = str(thing.get("label") or "").strip()
    if not label:
        return ""
    normalized = re.sub(
        r"\s*\(([^)]*)\)\s*",
        lambda match: " " if _is_detail_text(match.group(1)) else f" {match.group(1)} ",
        label,
    )
    return canonicalize_thing_key(normalized)


def _is_detail_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    if re.search(r"\d", text) and len(canonicalize_thing_key(text)) >= 6:
        return True
    return any(token in text for token in _DETAIL_TOKENS)


def _thing_type_key(thing: Mapping[str, Any]) -> str:
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    candidates = (
        props.get("thingTypeCategory"),
        props.get("model"),
        props.get("generatedLabel"),
        props.get("thingTypeTitle"),
        thing.get("thingTypeUID"),
        thing.get("thingTypeUid"),
    )
    text = " ".join(str(value or "") for value in candidates).lower()
    for key, tokens in _TYPE_TOKENS.items():
        if any(token in text for token in tokens):
            return key
    return ""


def _thing_serial_key(thing: Mapping[str, Any]) -> str:
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    return canonicalize_thing_key(
        props.get("serialNumber") or props.get("serial") or _thing_label_serial(thing)
    )


def _thing_label_serial(thing: Mapping[str, Any]) -> str:
    label = str(thing.get("label") or "").strip()
    for detail in re.findall(r"\(([^)]*)\)", label):
        text = str(detail or "").strip()
        if re.search(r"\d", text) and len(canonicalize_thing_key(text)) >= 6:
            return text
    return ""
