from __future__ import annotations

from enum import StrEnum
from types import SimpleNamespace

from .module_loader import load_component_module_with_stubs, make_module


class _SensorDeviceClass(StrEnum):
    BATTERY = "battery"
    CURRENT = "current"
    DURATION = "duration"
    ENERGY = "energy"
    FREQUENCY = "frequency"
    POWER = "power"
    TEMPERATURE = "temperature"
    VOLTAGE = "voltage"


class _SensorStateClass(StrEnum):
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


_package = "solarwatt_manager_sensor_meta_test"
sensor_meta = load_component_module_with_stubs(
    "sensor_meta",
    package_name=_package,
    stubs={
        "homeassistant": make_module("homeassistant"),
        "homeassistant.components": make_module("homeassistant.components"),
        "homeassistant.components.sensor": make_module(
            "homeassistant.components.sensor",
            SensorDeviceClass=_SensorDeviceClass,
            SensorStateClass=_SensorStateClass,
        ),
        "homeassistant.const": make_module(
            "homeassistant.const",
            PERCENTAGE="%",
            UnitOfElectricCurrent=SimpleNamespace(AMPERE="A"),
            UnitOfElectricPotential=SimpleNamespace(VOLT="V"),
            UnitOfEnergy=SimpleNamespace(KILO_WATT_HOUR="kWh", WATT_HOUR="Wh"),
            UnitOfFrequency=SimpleNamespace(HERTZ="Hz"),
            UnitOfPower=SimpleNamespace(KILO_WATT="kW", WATT="W"),
            UnitOfTemperature=SimpleNamespace(CELSIUS="°C"),
            UnitOfTime=SimpleNamespace(SECONDS="s"),
        ),
    },
)


def _percentage_meta(item_name: str):
    return sensor_meta.guess_ha_meta(
        "Number:Dimensionless",
        sensor_meta.ParsedState(50, "%"),
        item_name,
    )


def test_only_primary_state_of_charge_has_battery_device_class():
    assert (
        _percentage_meta("hems_battery_uuid_state_of_charge")["device_class"]
        == _SensorDeviceClass.BATTERY
    )
    assert "device_class" not in _percentage_meta(
        "hems_battery_uuid_backup_state_of_charge"
    )
    assert "device_class" not in _percentage_meta(
        "hems_battery_uuid_state_of_charge_minimum"
    )
