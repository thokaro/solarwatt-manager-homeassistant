from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)

from .state_parser import ParsedState


_SUGGESTED_UNIT_MAP: dict[str, Any] = {
    "W": UnitOfPower.WATT,
    "kW": UnitOfPower.KILO_WATT,
    "Wh": UnitOfEnergy.WATT_HOUR,
    "kWh": UnitOfEnergy.KILO_WATT_HOUR,
    "V": UnitOfElectricPotential.VOLT,
    "A": UnitOfElectricCurrent.AMPERE,
    "Hz": UnitOfFrequency.HERTZ,
    "°C": UnitOfTemperature.CELSIUS,
    "%": PERCENTAGE,
    "s": UnitOfTime.SECONDS,
    "sec": UnitOfTime.SECONDS,
}

_UNIT_DOMAIN_MAP: dict[str, str] = {
    "W": "power",
    "kW": "power",
    "Wh": "energy",
    "kWh": "energy",
    "V": "voltage",
    "A": "current",
    "Hz": "frequency",
    "°C": "temperature",
    "%": "percentage",
    "Ω": "resistance",
    "s": "duration",
    "sec": "duration",
}

_ITEM_TYPE_DOMAIN_MAP: tuple[tuple[str, str], ...] = (
    ("Number:Power", "power"),
    ("Number:Energy", "energy"),
    ("Number:Temperature", "temperature"),
    ("Number:Frequency", "frequency"),
    ("Number:ElectricCurrent", "current"),
    ("Number:ElectricPotential", "voltage"),
    ("Number:Dimensionless", "percentage"),
)

_CHANNEL_TYPE_UID_HINTS: tuple[tuple[str, str], ...] = (
    ("power-factor", "Number:Dimensionless"),
    ("powerfactor", "Number:Dimensionless"),
    ("electriccurrent", "Number:ElectricCurrent"),
    ("current", "Number:ElectricCurrent"),
    ("electricpotential", "Number:ElectricPotential"),
    ("voltage", "Number:ElectricPotential"),
    ("temperature", "Number:Temperature"),
    ("frequency", "Number:Frequency"),
    ("energy", "Number:Energy"),
    ("power", "Number:Power"),
    ("percentage", "Number:Dimensionless"),
)

_DOMAIN_META: dict[str, dict[str, Any]] = {
    "power": {
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": UnitOfPower.WATT,
    },
    "temperature": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": UnitOfTemperature.CELSIUS,
    },
    "frequency": {
        "device_class": SensorDeviceClass.FREQUENCY,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": UnitOfFrequency.HERTZ,
    },
    "current": {
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": UnitOfElectricCurrent.AMPERE,
    },
    "voltage": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": UnitOfElectricPotential.VOLT,
    },
    "duration": {
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "default_unit": UnitOfTime.SECONDS,
    },
    "percentage": {"state_class": SensorStateClass.MEASUREMENT},
    "resistance": {"state_class": SensorStateClass.MEASUREMENT},
}

_BATTERY_PERCENTAGE_TOKENS = ("soc", "stateofcharge", "battery", "akku")
_PERCENT_CHANNEL_HINTS = ("power-factor", "powerfactor", "percentage")


def guess_ha_meta(
    oh_type: str | None,
    parsed: ParsedState,
    item_name: str | None = None,
    channel_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map OpenHAB/SOLARWATT state metadata to Home Assistant sensor metadata."""
    channel_item_type = _typed_channel_item_type(channel_metadata)
    effective_oh_type = channel_item_type or oh_type
    unit = (parsed.unit if parsed else None) or _unit_from_channel_metadata(channel_metadata)
    name_l = (item_name or "").lower()
    total_increasing_energy = _is_total_increasing_energy(name_l, channel_metadata)
    name_domain = (
        "duration"
        if name_l.endswith("seconds") or name_l.endswith("sec")
        else "temperature"
        if "temperature" in name_l or "temperatur" in name_l
        else None
    )

    meta: dict[str, Any] = {"suggested_unit": _SUGGESTED_UNIT_MAP.get(unit, unit)}

    seed_domain = name_domain or _UNIT_DOMAIN_MAP.get(unit or "")
    if seed_domain:
        _apply_domain_meta(
            meta,
            seed_domain,
            total_increasing_energy=total_increasing_energy,
            name_l=name_l,
            set_default_unit=unit is None and name_domain is not None,
        )

    if "icon" not in meta:
        if any(k in name_l for k in ("pv", "solar", "generator")):
            meta["icon"] = "mdi:solar-power"
        elif any(k in name_l for k in ("grid", "netz")):
            meta["icon"] = "mdi:transmission-tower"
        elif any(k in name_l for k in ("battery", "akku")):
            meta["icon"] = "mdi:battery"
        elif any(k in name_l for k in ("house", "home", "load", "verbrauch")):
            meta["icon"] = "mdi:home-lightning-bolt"

    if not effective_oh_type or name_domain == "duration":
        return meta

    item_type_domain = _domain_from_item_type(effective_oh_type)
    if item_type_domain:
        _apply_domain_meta(
            meta,
            item_type_domain,
            total_increasing_energy=total_increasing_energy,
            name_l=name_l,
            set_default_unit=unit is None,
        )
        return meta

    return meta


def _typed_channel_item_type(channel_metadata: Mapping[str, Any] | None) -> str | None:
    """Return the most useful typed item_type from channel metadata."""
    if not channel_metadata:
        return None

    for key in ("harmonized_item_type", "item_type"):
        value = str(channel_metadata.get(key) or "").strip()
        if _is_specific_item_type(value):
            return value

    inferred_type = _item_type_from_channel_type_uid(
        str(channel_metadata.get("channel_type_uid") or "").strip()
    )
    if inferred_type:
        return inferred_type

    for key in ("harmonized_item_type", "item_type"):
        value = str(channel_metadata.get(key) or "").strip()
        if value:
            return value

    return None


def _is_specific_item_type(item_type: str) -> bool:
    """Return True when item_type already carries a specific numeric domain."""
    return bool(item_type) and item_type not in {"String", "Number"}


def _item_type_from_channel_type_uid(channel_type_uid: str) -> str | None:
    """Infer a typed HA/OpenHAB item type from channelTypeUID when itemType is vague."""
    uid = channel_type_uid.lower()
    if not uid:
        return None

    for token, item_type in _CHANNEL_TYPE_UID_HINTS:
        if token in uid:
            return item_type

    return None


def _domain_from_item_type(item_type: str) -> str | None:
    """Return the normalized sensor domain implied by an OpenHAB item type."""
    for prefix, domain in _ITEM_TYPE_DOMAIN_MAP:
        if item_type.startswith(prefix):
            return domain
    return None


def _unit_from_channel_metadata(channel_metadata: Mapping[str, Any] | None) -> str | None:
    """Infer a unit from thing channel metadata when the item state has none."""
    if not channel_metadata:
        return None

    channel_type_uid = str(channel_metadata.get("channel_type_uid") or "").strip().lower()
    channel_label = str(channel_metadata.get("channel_label") or "").strip().lower()
    return "%" if any(token in channel_type_uid for token in _PERCENT_CHANNEL_HINTS) or "%" in channel_label else None


def _apply_domain_meta(
    meta: dict[str, Any],
    domain: str,
    *,
    total_increasing_energy: bool,
    name_l: str,
    set_default_unit: bool = False,
) -> None:
    """Apply device/state class metadata for one normalized sensor domain."""
    if domain == "energy":
        meta["device_class"] = SensorDeviceClass.ENERGY
        meta["state_class"] = (
            SensorStateClass.TOTAL_INCREASING
            if total_increasing_energy
            else SensorStateClass.TOTAL
        )
        if set_default_unit:
            meta["suggested_unit"] = UnitOfEnergy.KILO_WATT_HOUR
        return

    config = _DOMAIN_META.get(domain)
    if not config:
        return

    if device_class := config.get("device_class"):
        meta["device_class"] = device_class
    meta["state_class"] = config["state_class"]

    if set_default_unit and (default_unit := config.get("default_unit")) is not None:
        meta["suggested_unit"] = default_unit

    if domain != "percentage":
        return

    if any(token in name_l for token in _BATTERY_PERCENTAGE_TOKENS):
        meta["device_class"] = SensorDeviceClass.BATTERY


def _is_total_increasing_energy(
    item_name: str,
    channel_metadata: Mapping[str, Any] | None,
) -> bool:
    """Return True when an energy item is clearly a cumulative counter."""
    total_tokens = (
        "_total",
        "total_",
        "etotal",
        "aggregated",
        "cumulative",
        "cumulated",
        "kumulativ",
        "extrapolated",
        "lifetime",
    )
    if any(token in item_name for token in total_tokens):
        return True

    if not channel_metadata:
        return False

    label = str(channel_metadata.get("channel_label") or "").strip().lower()
    return any(
        token in label
        for token in (
            "total",
            "etotal",
            "aggregated",
            "cumulative",
            "gesamt",
            "kumulativ",
            "extrapolated",
            "lifetime",
        )
    )
