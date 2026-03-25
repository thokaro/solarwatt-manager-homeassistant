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


def guess_ha_meta(
    oh_type: str | None,
    parsed: ParsedState,
    item_name: str | None = None,
    channel_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map OpenHAB/SOLARWATT state metadata to Home Assistant sensor metadata."""
    channel_item_type = _typed_channel_item_type(channel_metadata)
    effective_oh_type = channel_item_type or oh_type
    unit = parsed.unit if parsed else None
    name_l = (item_name or "").lower()
    duration_name = name_l.endswith("seconds") or name_l.endswith("sec")
    temperature_name = "temperature" in name_l or "temperatur" in name_l

    unit_map: dict[str, Any] = {
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

    meta: dict[str, Any] = {"suggested_unit": unit_map.get(unit, unit)}

    if duration_name:
        meta.update(
            {
                "device_class": SensorDeviceClass.DURATION,
                "state_class": SensorStateClass.MEASUREMENT,
            }
        )
        if unit is None:
            meta["suggested_unit"] = UnitOfTime.SECONDS
    elif temperature_name:
        meta.update(
            {
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            }
        )
        if unit is None:
            meta["suggested_unit"] = UnitOfTemperature.CELSIUS
    else:
        if unit in ("W", "kW"):
            meta.update(
                {
                    "device_class": SensorDeviceClass.POWER,
                    "state_class": SensorStateClass.MEASUREMENT,
                }
            )
        elif unit in ("kWh", "Wh"):
            meta.update(
                {
                    "device_class": SensorDeviceClass.ENERGY,
                    "state_class": SensorStateClass.TOTAL_INCREASING,
                }
            )
        elif unit in ("V",):
            meta.update(
                {
                    "device_class": SensorDeviceClass.VOLTAGE,
                    "state_class": SensorStateClass.MEASUREMENT,
                }
            )
        elif unit in ("A",):
            meta.update(
                {
                    "device_class": SensorDeviceClass.CURRENT,
                    "state_class": SensorStateClass.MEASUREMENT,
                }
            )
        elif unit in ("Hz",):
            meta.update(
                {
                    "device_class": SensorDeviceClass.FREQUENCY,
                    "state_class": SensorStateClass.MEASUREMENT,
                }
            )
        elif unit in ("°C",):
            meta.update(
                {
                    "device_class": SensorDeviceClass.TEMPERATURE,
                    "state_class": SensorStateClass.MEASUREMENT,
                }
            )
        elif unit == "%":
            meta["state_class"] = SensorStateClass.MEASUREMENT
            if any(k in name_l for k in ("soc", "stateofcharge", "battery", "akku")):
                meta["device_class"] = SensorDeviceClass.BATTERY
        elif unit in ("Ω",):
            meta.update({"state_class": SensorStateClass.MEASUREMENT})

    if "icon" not in meta:
        if any(k in name_l for k in ("pv", "solar", "generator")):
            meta["icon"] = "mdi:solar-power"
        elif any(k in name_l for k in ("grid", "netz")):
            meta["icon"] = "mdi:transmission-tower"
        elif any(k in name_l for k in ("battery", "akku")):
            meta["icon"] = "mdi:battery"
        elif any(k in name_l for k in ("house", "home", "load", "verbrauch")):
            meta["icon"] = "mdi:home-lightning-bolt"

    if not effective_oh_type or duration_name:
        return meta

    if effective_oh_type.startswith("Number:Power"):
        meta["device_class"] = SensorDeviceClass.POWER
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfPower.WATT
        return meta

    if effective_oh_type.startswith("Number:Energy"):
        meta["device_class"] = SensorDeviceClass.ENERGY
        meta["state_class"] = SensorStateClass.TOTAL_INCREASING
        if unit is None:
            meta["suggested_unit"] = UnitOfEnergy.KILO_WATT_HOUR
        return meta

    if effective_oh_type.startswith("Number:Temperature"):
        meta["device_class"] = SensorDeviceClass.TEMPERATURE
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfTemperature.CELSIUS
        return meta

    if effective_oh_type.startswith("Number:Frequency"):
        meta["device_class"] = SensorDeviceClass.FREQUENCY
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfFrequency.HERTZ
        return meta

    if effective_oh_type.startswith("Number:ElectricCurrent"):
        meta["device_class"] = SensorDeviceClass.CURRENT
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfElectricCurrent.AMPERE
        return meta

    if effective_oh_type.startswith("Number:ElectricPotential"):
        meta["device_class"] = SensorDeviceClass.VOLTAGE
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit is None:
            meta["suggested_unit"] = UnitOfElectricPotential.VOLT
        return meta

    if effective_oh_type.startswith("Number:Dimensionless"):
        meta["state_class"] = SensorStateClass.MEASUREMENT
        if unit == "%":
            meta["device_class"] = SensorDeviceClass.BATTERY
        return meta

    return meta


def _typed_channel_item_type(channel_metadata: Mapping[str, Any] | None) -> str | None:
    """Return the most useful typed item_type from channel metadata."""
    if not channel_metadata:
        return None

    for key in ("harmonized_item_type", "item_type"):
        value = str(channel_metadata.get(key) or "").strip()
        if value and value != "String":
            return value

    value = str(channel_metadata.get("item_type") or "").strip()
    return value or None
