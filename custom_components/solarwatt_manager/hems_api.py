from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any


ENERGY_OVERVIEW_PATH = "/rest/hems-configurator/energy-overview"
THINGS_PATH = "/rest/hems-configurator/things"

_POWER_ITEM_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("production", "energy_overview_pv_production", "PV production"),
    ("feedIn", "energy_overview_grid_feed_in", "Grid feed in"),
    ("feedOut", "energy_overview_grid_import", "Grid import"),
    (
        "householdConsumption",
        "energy_overview_household_consumption",
        "Household consumption",
    ),
    ("storagePowerIn", "energy_overview_battery_charge", "Battery charge"),
    ("storagePowerOut", "energy_overview_battery_discharge", "Battery discharge"),
)


def energy_overview_to_items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Convert the newer HEMS energy overview response to OpenHAB-like items."""
    items = [
        _power_item(item_name, label, payload.get(source_key), "energy_overview")
        for source_key, item_name, label in _POWER_ITEM_DEFINITIONS
        if source_key in payload
    ]
    return items


def energy_overview_to_legacy_items(
    payload: Mapping[str, Any],
    things: Sequence[Any],
) -> list[dict[str, Any]]:
    """Build legacy item names from the HEMS overview for existing entity IDs."""
    items: list[dict[str, Any]] = []
    ids_by_category = _thing_ids_by_category(things)

    if location_id := ids_by_category.get("location"):
        items.extend(
            _legacy_power_items(
                location_id,
                "harmonized",
                (
                    ("power_produced", "Power Produced", payload.get("production")),
                    ("power_consumed", "Power Consumed", payload.get("householdConsumption")),
                    ("power_consumed_from_grid", "Power Consumed From Grid", payload.get("feedOut")),
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
                    (
                        "power_self_consumed",
                        "Power Self Consumed",
                        _self_consumed_power(payload),
                    ),
                ),
            )
        )

    if pvplant_id := ids_by_category.get("pvplant"):
        items.extend(
            _legacy_power_items(
                pvplant_id,
                "harmonized",
                (("power_out", "Power Out", payload.get("production")),),
            )
        )

    if inverter_id := ids_by_category.get("inverter"):
        items.extend(
            _legacy_power_items(
                inverter_id,
                "",
                (
                    (
                        "inverter_total_pv_input_power",
                        "Inverter Total PV Input Power",
                        payload.get("production"),
                    ),
                    (
                        "electricData_mppt_total_power",
                        "electricData MPPT Total Power",
                        payload.get("production"),
                    ),
                ),
            )
        )
        items.extend(
            _legacy_power_items(
                inverter_id,
                "harmonized",
                (
                    ("mppt_dc_power", "MPPT DC Power", payload.get("production")),
                    ("power_out", "Power Out", payload.get("production")),
                ),
            )
        )

    if meter_id := ids_by_category.get("meter"):
        items.extend(
            _legacy_power_items(
                meter_id,
                "harmonized",
                (
                    ("power_in", "Power In", payload.get("feedOut")),
                    ("power_out", "Power Out", payload.get("feedIn")),
                ),
            )
        )
        items.append(
            _power_item(
                f"{_item_prefix(meter_id)}_meter_active_power_total",
                "Meter Active Power Total",
                _net_grid_power(payload),
                "energy_overview",
            )
        )

    if battery_id := ids_by_category.get("battery"):
        items.extend(
            _legacy_power_items(
                battery_id,
                "harmonized",
                (
                    ("power_in", "Power In", payload.get("storagePowerIn")),
                    ("power_out", "Power Out", payload.get("storagePowerOut")),
                ),
            )
        )
        items.extend(
            _legacy_power_items(
                battery_id,
                "battery",
                (
                    ("battery_calculated_power", "Battery Calculated Power", _net_battery_power(payload)),
                    ("bms_power", "Battery BMS Power", _net_battery_power(payload)),
                    ("bms_1_power", "Battery BMS 1 Power", _net_battery_power(payload)),
                ),
            )
        )

    return items


def battery_soc_to_legacy_items(
    things: Sequence[Any],
    soc: int | float,
) -> list[dict[str, Any]]:
    """Build legacy battery SoC item names from an inverter Modbus read."""
    ids_by_category = _thing_ids_by_category(things)
    battery_id = ids_by_category.get("battery")
    if not battery_id:
        return []

    prefix = _item_prefix(battery_id)
    return [
        _battery_item(
            f"{prefix}_battery_bms_soc",
            "Battery BMS SoC",
            soc,
        ),
        _battery_item(
            f"{prefix}_battery_bms_1_soc",
            "Battery BMS 1 SoC",
            soc,
        ),
    ]


def things_to_openhab_things(payload: Sequence[Any]) -> list[dict[str, Any]]:
    """Convert newer HEMS thing records to the shape used by existing diagnostics."""
    things: list[dict[str, Any]] = []
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


def _battery_item(
    name: str,
    label: str,
    value: int | float,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "state": _percentage_state(value),
        "type": "Number:Dimensionless",
        "editable": False,
        "category": "energy_overview",
        "stateDescription": {"pattern": "%.0f %%"},
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


def _thing_ids_by_category(things: Sequence[Any]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for raw_thing in things:
        if not isinstance(raw_thing, Mapping):
            continue
        thing_id = str(raw_thing.get("id") or "").strip()
        if not thing_id:
            continue
        thing_type = raw_thing.get("thingType")
        thing_type = thing_type if isinstance(thing_type, Mapping) else {}
        type_id = str(thing_type.get("id") or "").strip().lower()
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


def _percentage_state(value: int | float) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return f"{int(numeric)} %"
    return f"{numeric} %"


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
