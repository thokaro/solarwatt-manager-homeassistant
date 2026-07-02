from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any


ENERGY_OVERVIEW_PATH = "/rest/hems-configurator/energy-overview"
THINGS_PATH = "/rest/hems-configurator/things"
HEMS_THING_PROPERTY = "solarwatt.hemsConfigurator"
ENERGY_OVERVIEW_THING_PROPERTY = "solarwatt.energyOverview"
ENERGY_OVERVIEW_THING_UID = "energy-overview:standard:energy-overview"

_ENERGY_OVERVIEW_ITEM_NAMES = (
    "production",
    "feedIn",
    "feedOut",
    "householdConsumption",
    "storagePowerIn",
    "storagePowerOut",
    "gridPower",
    "batteryPower",
    "selfConsumedPower",
    "batteryChargePower",
    "batteryDischargePower",
)
_ENERGY_OVERVIEW_ITEM_NAME_SET = set(_ENERGY_OVERVIEW_ITEM_NAMES)


def energy_overview_to_items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Convert the HEMS energy overview response to OpenHAB-like items."""
    values = _energy_overview_values(payload)
    return [
        _power_item(item_name, item_name, values.get(item_name), "energy_overview")
        for item_name in _ENERGY_OVERVIEW_ITEM_NAMES
        if item_name in values
    ]


def energy_overview_to_legacy_items(
    payload: Mapping[str, Any],
    things: Sequence[Any],
) -> list[dict[str, Any]]:
    """Build legacy item names from HEMS overview data for existing entity IDs."""
    items: list[dict[str, Any]] = []
    ids_by_category = _thing_ids_by_category(things)

    if location_id := ids_by_category.get("location"):
        items.extend(_location_legacy_items(location_id, payload))

    if pvplant_id := ids_by_category.get("pvplant"):
        items.extend(_pvplant_legacy_items(pvplant_id, payload))

    if inverter_id := ids_by_category.get("inverter"):
        items.extend(_inverter_legacy_items(inverter_id, payload))

    if meter_id := ids_by_category.get("meter"):
        items.extend(_meter_legacy_items(meter_id, payload))

    if battery_id := ids_by_category.get("battery"):
        items.extend(_battery_legacy_items(battery_id, payload))

    return items

def _energy_overview_values(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return raw and derived values from the HEMS energy overview response."""
    values: dict[str, Any] = {
        item_name: payload.get(item_name)
        for item_name in (
            "production",
            "feedIn",
            "feedOut",
            "householdConsumption",
            "storagePowerIn",
            "storagePowerOut",
        )
        if item_name in payload
    }

    derived_values = {
        "gridPower": _net_grid_power(payload),
        "batteryPower": _net_battery_power(payload),
        "selfConsumedPower": _self_consumed_power(payload),
        "batteryChargePower": _battery_charge_power(payload),
        "batteryDischargePower": _battery_discharge_power(payload),
    }

    values.update(
        {
            key: value
            for key, value in derived_values.items()
            if value is not None
        }
    )
    return values

def item_names_to_thing_uids(
    item_names: Sequence[Any],
    things: Sequence[Any],
) -> dict[str, str]:
    """Map generated legacy HEMS item names back to their owning things."""
    thing_prefixes: list[tuple[str, str]] = []
    for raw_thing in things:
        if not isinstance(raw_thing, Mapping):
            continue
        thing_uid = str(
            raw_thing.get("UID") or raw_thing.get("uid") or raw_thing.get("id") or ""
        ).strip()
        if not thing_uid:
            continue
        if prefix := _item_prefix(thing_uid):
            thing_prefixes.append((prefix, thing_uid))

    thing_prefixes.sort(key=lambda item: len(item[0]), reverse=True)

    item_to_thing_uid: dict[str, str] = {}
    for raw_item_name in item_names:
        item_name = str(raw_item_name or "").strip()
        if not item_name:
            continue
        if item_name in _ENERGY_OVERVIEW_ITEM_NAME_SET:
            item_to_thing_uid[item_name] = ENERGY_OVERVIEW_THING_UID
            continue
        for prefix, thing_uid in thing_prefixes:
            if item_name == prefix or item_name.startswith(f"{prefix}_"):
                item_to_thing_uid[item_name] = thing_uid
                break

    return item_to_thing_uid


def things_to_openhab_things(payload: Sequence[Any]) -> list[dict[str, Any]]:
    """Convert HEMS thing records to the shape used by existing diagnostics."""
    things: list[dict[str, Any]] = [_energy_overview_thing()]
    for raw_thing in payload:
        if not isinstance(raw_thing, Mapping):
            continue
        uid = str(raw_thing.get("id") or "").strip()
        if not uid:
            continue

        thing_type = raw_thing.get("thingType")
        thing_type = thing_type if isinstance(thing_type, Mapping) else {}
        type_uid = str(thing_type.get("id") or "").strip()
        responsible_bridge = raw_thing.get("responsibleBridge")
        responsible_bridge = (
            responsible_bridge if isinstance(responsible_bridge, Mapping) else {}
        )

        properties = _thing_properties(raw_thing, thing_type)
        properties[HEMS_THING_PROPERTY] = "true"
        thing: dict[str, Any] = {
            "UID": uid,
            "uid": uid,
            "label": raw_thing.get("label") or uid,
            "thingTypeUID": type_uid,
            "thingTypeUid": type_uid,
            "statusInfo": raw_thing.get("statusInfo") or {},
            "properties": properties,
            "channels": [],
        }
        if bridge_uid := str(responsible_bridge.get("id") or "").strip():
            thing["bridgeUID"] = bridge_uid
            thing["bridgeUid"] = bridge_uid
        things.append(thing)
    return things


def is_hems_thing(thing: Mapping[str, Any]) -> bool:
    """Return True for synthetic thing records converted from HEMS configurator data."""
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    return str(props.get(HEMS_THING_PROPERTY) or "").strip().lower() == "true"


def is_energy_overview_thing(thing: Mapping[str, Any]) -> bool:
    """Return True for the synthetic Energy Overview device."""
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    return str(props.get(ENERGY_OVERVIEW_THING_PROPERTY) or "").strip().lower() == "true"


def _energy_overview_thing() -> dict[str, Any]:
    return {
        "UID": ENERGY_OVERVIEW_THING_UID,
        "uid": ENERGY_OVERVIEW_THING_UID,
        "label": "Energy Overview",
        "thingTypeUID": "energy-overview:standard",
        "thingTypeUid": "energy-overview:standard",
        "statusInfo": {"status": "ONLINE", "statusDetail": "NONE"},
        "properties": {
            HEMS_THING_PROPERTY: "true",
            ENERGY_OVERVIEW_THING_PROPERTY: "true",
            "thingTypeTitle": "Energy Overview",
            "thingTypeCategory": "ENERGY_OVERVIEW",
        },
        "channels": [],
    }


def _power_item(
    name: str,
    label: str,
    value: Any,
    category: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "state": _power_state(value),
        "type": "Number:Power",
        "editable": False,
        "category": category,
        "stateDescription": {"pattern": "%.0f W"},
    }


def _legacy_power_items(
    thing_id: str,
    group: str,
    definitions: Sequence[tuple[str, str, Any]],
) -> list[dict[str, Any]]:
    prefix = _item_prefix(thing_id)
    group_prefix = f"{group}_" if group else ""
    return [
        _power_item(
            f"{prefix}_{group_prefix}{suffix}",
            label,
            value,
            "energy_overview",
        )
        for suffix, label, value in definitions
        if value is not None
    ]


def _location_legacy_items(
    thing_id: str,
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return _legacy_power_items(
        thing_id,
        "harmonized",
        (
            ("power_produced", "Power Produced", payload.get("production")),
            ("power_consumed", "Power Consumed", payload.get("householdConsumption")),
            (
                "power_consumed_from_grid",
                "Power Consumed From Grid",
                payload.get("feedOut"),
            ),
            ("power_out", "Power Out", payload.get("feedIn")),
            ("power_buffered", "Power Buffered", payload.get("storagePowerIn")),
            ("power_released", "Power Released", payload.get("storagePowerOut")),
            (
                "power_consumed_from_storage",
                "Power Consumed From Storage",
                payload.get("storagePowerOut"),
            ),
            (
                "power_out_from_storage",
                "Power Out From Storage",
                payload.get("storagePowerOut"),
            ),
            (
                "power_buffered_from_producers",
                "Power Buffered From Producers",
                payload.get("storagePowerIn"),
            ),
            ("power_self_consumed", "Power Self Consumed", _self_consumed_power(payload)),
        ),
    )


def _pvplant_legacy_items(
    thing_id: str,
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return _legacy_power_items(
        thing_id,
        "harmonized",
        (("power_out", "Power Out", payload.get("production")),),
    )


def _inverter_legacy_items(
    thing_id: str,
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        *_legacy_power_items(
            thing_id,
            "",
            (
                (
                    "inverter_total_pv_input_power",
                    "Inverter Total PV Input Power",
                    payload.get("production"),
                ),
                (
                    "electricData_mppt_total_power",
                    "ElectricData MPPT Total Power",
                    payload.get("production"),
                ),
            ),
        ),
        *_legacy_power_items(
            thing_id,
            "harmonized",
            (
                ("mppt_dc_power", "MPPT DC Power", payload.get("production")),
                ("power_out", "Power Out", payload.get("production")),
            ),
        ),
    ]


def _meter_legacy_items(
    thing_id: str,
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        *_legacy_power_items(
            thing_id,
            "harmonized",
            (
                ("power_in", "Power In", payload.get("feedOut")),
                ("power_out", "Power Out", payload.get("feedIn")),
            ),
        ),
        _power_item(
            f"{_item_prefix(thing_id)}_meter_active_power_total",
            "Meter Active Power Total",
            _net_grid_power(payload),
            "energy_overview",
        ),
    ]


def _battery_legacy_items(
    thing_id: str,
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    net_battery_power = _net_battery_power(payload)
    return [
        *_legacy_power_items(
            thing_id,
            "harmonized",
            (
                ("power_in", "Power In", payload.get("storagePowerIn")),
                ("power_out", "Power Out", payload.get("storagePowerOut")),
            ),
        ),
        *_legacy_power_items(
            thing_id,
            "battery",
            (
                (
                    "battery_calculated_power",
                    "Battery Calculated Power",
                    net_battery_power,
                ),
                ("bms_power", "Battery BMS Power", net_battery_power),
                ("bms_1_power", "Battery BMS 1 Power", net_battery_power),
            ),
        ),
    ]


def _thing_ids_by_category(things: Sequence[Any]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for raw_thing in things:
        if not isinstance(raw_thing, Mapping):
            continue
        thing_id = str(
            raw_thing.get("id") or raw_thing.get("UID") or raw_thing.get("uid") or ""
        ).strip()
        if not thing_id:
            continue
        thing_type = raw_thing.get("thingType")
        thing_type = thing_type if isinstance(thing_type, Mapping) else {}
        type_id = str(
            thing_type.get("id")
            or raw_thing.get("thingTypeUID")
            or raw_thing.get("thingTypeUid")
            or ""
        ).strip().lower()
        category = thing_type.get("category")
        category = category if isinstance(category, Mapping) else {}
        category_type = str(category.get("type") or "").strip().upper()

        if "kiwigrid-location" in type_id:
            ids.setdefault("location", thing_id)
        elif type_id.startswith("pvplant:"):
            ids.setdefault("pvplant", thing_id)
        elif "inverter" in type_id and "bridge" not in type_id:
            ids.setdefault("inverter", thing_id)
        elif "battery" in type_id or category_type == "STORAGES":
            ids.setdefault("battery", thing_id)
        elif "meter" in type_id or category_type == "POWER_METERS":
            ids.setdefault("meter", thing_id)
    return ids


def _item_prefix(thing_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", thing_id).strip("_")


def _power_state(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return "NULL"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "NULL"
    if numeric.is_integer():
        return f"{int(numeric)} W"
    return f"{numeric} W"


def _numeric_value(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _net_grid_power(payload: Mapping[str, Any]) -> float | None:
    feed_out = _numeric_value(payload, "feedOut")
    feed_in = _numeric_value(payload, "feedIn")
    if feed_out is None and feed_in is None:
        return None
    return (feed_out or 0) - (feed_in or 0)


def _net_battery_power(payload: Mapping[str, Any]) -> float | None:
    storage_out = _numeric_value(payload, "storagePowerOut")
    storage_in = _numeric_value(payload, "storagePowerIn")
    if storage_out is None and storage_in is None:
        return None
    return (storage_out or 0) - (storage_in or 0)


def _self_consumed_power(payload: Mapping[str, Any]) -> float | None:
    production = _numeric_value(payload, "production")
    feed_in = _numeric_value(payload, "feedIn")
    if production is None and feed_in is None:
        return None
    return max((production or 0) - (feed_in or 0), 0)

def _battery_charge_power(payload: Mapping[str, Any]) -> float | None:
    return _numeric_value(payload, "storagePowerIn")


def _battery_discharge_power(payload: Mapping[str, Any]) -> float | None:
    return _numeric_value(payload, "storagePowerOut")

def _thing_properties(
    raw_thing: Mapping[str, Any],
    thing_type: Mapping[str, Any],
) -> dict[str, str]:
    category = thing_type.get("category")
    category = category if isinstance(category, Mapping) else {}
    properties: dict[str, str] = {}
    for key, value in (
        ("serialNumber", raw_thing.get("serialNumber")),
        ("thingTypeTitle", thing_type.get("title")),
        ("thingTypeCategory", category.get("type")),
    ):
        if text := str(value or "").strip():
            properties[key] = text
    return properties
