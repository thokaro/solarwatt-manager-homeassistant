from __future__ import annotations

from .module_loader import load_component_module

hems_api = load_component_module("hems_api")
energy_overview_to_items = hems_api.energy_overview_to_items
energy_overview_to_legacy_items = hems_api.energy_overview_to_legacy_items
battery_soc_to_legacy_items = hems_api.battery_soc_to_legacy_items
things_to_openhab_things = hems_api.things_to_openhab_things


def test_energy_overview_to_items_builds_power_items():
    items = energy_overview_to_items(
        {
            "production": 240,
            "feedIn": 0,
            "feedOut": 7.5,
            "householdConsumption": 426,
            "storagePowerIn": None,
            "storagePowerOut": 178,
        }
    )

    assert [item["name"] for item in items] == [
        "energy_overview_pv_production",
        "energy_overview_grid_feed_in",
        "energy_overview_grid_import",
        "energy_overview_household_consumption",
        "energy_overview_battery_charge",
        "energy_overview_battery_discharge",
    ]
    assert [item["state"] for item in items] == [
        "240 W",
        "0 W",
        "7.5 W",
        "426 W",
        "NULL",
        "178 W",
    ]
    assert all(item["type"] == "Number:Power" for item in items)


def test_energy_overview_to_legacy_items_builds_existing_power_names():
    items = energy_overview_to_legacy_items(
        {
            "production": 329,
            "feedIn": 0,
            "feedOut": 9,
            "householdConsumption": 445,
            "storagePowerIn": 0,
            "storagePowerOut": 107,
        },
        [
            {
                "id": "kiwigrid-location:standard:location-id",
                "thingType": {"id": "kiwigrid-location:standard"},
            },
            {
                "id": "pvplant:standard:pv-id",
                "thingType": {"id": "pvplant:standard"},
            },
            {
                "id": "foxesshybrid:inverter:serial",
                "thingType": {"id": "foxesshybrid:inverter"},
            },
            {
                "id": "foxesshybrid:meter:serial",
                "thingType": {
                    "id": "foxesshybrid:meter",
                    "category": {"type": "POWER_METERS"},
                },
            },
            {
                "id": "foxesshybrid:battery:serial",
                "thingType": {
                    "id": "foxesshybrid:battery",
                    "category": {"type": "STORAGES"},
                },
            },
        ],
    )

    states = {item["name"]: item["state"] for item in items}
    assert states["kiwigrid_location_standard_location_id_harmonized_power_consumed"] == "445 W"
    assert states["kiwigrid_location_standard_location_id_harmonized_power_consumed_from_grid"] == "9 W"
    assert states["pvplant_standard_pv_id_harmonized_power_out"] == "329 W"
    assert states["foxesshybrid_inverter_serial_inverter_total_pv_input_power"] == "329 W"
    assert states["foxesshybrid_meter_serial_harmonized_power_in"] == "9 W"
    assert states["foxesshybrid_meter_serial_harmonized_power_out"] == "0 W"
    assert states["foxesshybrid_meter_serial_meter_active_power_total"] == "9 W"
    assert states["foxesshybrid_battery_serial_harmonized_power_in"] == "0 W"
    assert states["foxesshybrid_battery_serial_harmonized_power_out"] == "107 W"


def test_battery_soc_to_legacy_items_builds_existing_soc_names():
    items = battery_soc_to_legacy_items(
        [
            {
                "id": "foxesshybrid:battery:serial",
                "thingType": {
                    "id": "foxesshybrid:battery",
                    "category": {"type": "STORAGES"},
                },
            },
        ],
        56,
    )

    assert items == [
        {
            "name": "foxesshybrid_battery_serial_battery_bms_soc",
            "label": "Battery BMS SoC",
            "state": "56 %",
            "type": "Number:Dimensionless",
            "editable": False,
            "category": "energy_overview",
            "stateDescription": {"pattern": "%.0f %%"},
        },
        {
            "name": "foxesshybrid_battery_serial_battery_bms_1_soc",
            "label": "Battery BMS 1 SoC",
            "state": "56 %",
            "type": "Number:Dimensionless",
            "editable": False,
            "category": "energy_overview",
            "stateDescription": {"pattern": "%.0f %%"},
        },
    ]


def test_things_to_openhab_things_preserves_diagnostics_metadata():
    things = things_to_openhab_things(
        [
            {
                "id": "foxesshybrid:inverter:123",
                "label": "SOLARWATT Inverter",
                "thingType": {
                    "id": "foxesshybrid:inverter",
                    "title": "SOLARWATT Inverter vision",
                    "category": {"type": "INVERTERS"},
                },
                "statusInfo": {"status": "ONLINE", "statusDetail": "NONE"},
                "serialNumber": "123",
                "responsibleBridge": {"id": "foxesshybrid:bridge:123"},
            },
            {"label": "Missing id"},
        ]
    )

    assert things == [
        {
            "UID": "foxesshybrid:inverter:123",
            "uid": "foxesshybrid:inverter:123",
            "label": "SOLARWATT Inverter",
            "thingTypeUID": "foxesshybrid:inverter",
            "thingTypeUid": "foxesshybrid:inverter",
            "statusInfo": {"status": "ONLINE", "statusDetail": "NONE"},
            "properties": {
                "serialNumber": "123",
                "thingTypeTitle": "SOLARWATT Inverter vision",
                "thingTypeCategory": "INVERTERS",
            },
            "channels": [],
            "bridgeUID": "foxesshybrid:bridge:123",
            "bridgeUid": "foxesshybrid:bridge:123",
        }
    ]
