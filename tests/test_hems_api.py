from __future__ import annotations

from .module_loader import load_component_module

hems_api = load_component_module("hems_api")
energy_overview_to_items = hems_api.energy_overview_to_items
energy_overview_to_legacy_items = hems_api.energy_overview_to_legacy_items
is_energy_overview_thing = hems_api.is_energy_overview_thing
is_hems_thing = hems_api.is_hems_thing
item_names_to_thing_uids = hems_api.item_names_to_thing_uids
KIWIGRID_FLOW_THING_UID = hems_api.KIWIGRID_FLOW_THING_UID
kiwigrid_flow_thing = hems_api.kiwigrid_flow_thing
things_to_openhab_things = hems_api.things_to_openhab_things


def test_energy_overview_to_items_builds_power_items():
    items = energy_overview_to_items(
        {
            "production": 730,
            "feedIn": 501,
            "feedOut": 0,
            "householdConsumption": 229,
            "storagePowerIn": 0,
            "storagePowerOut": 0,
        }
    )

    assert [item["name"] for item in items] == [
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
        "householdFromBatteryPower",
        "householdFromGridPower",
        "householdFromPvPower",
    ]
    assert [item["state"] for item in items] == [
        "730 W",
        "501 W",
        "0 W",
        "229 W",
        "0 W",
        "0 W",
        "-501 W",
        "0 W",
        "229 W",
        "0 W",
        "0 W",
        "0 W",
        "0 W",
        "229 W",
    ]
    assert all(item["type"] == "Number:Power" for item in items)


def test_energy_overview_to_items_builds_household_source_power_items():
    items = energy_overview_to_items(
        {
            "production": 0,
            "feedIn": 0,
            "feedOut": 10,
            "householdConsumption": 955,
            "storagePowerIn": 0,
            "storagePowerOut": 945,
        }
    )

    states = {item["name"]: item["state"] for item in items}
    assert states["householdFromBatteryPower"] == "945 W"
    assert states["householdFromGridPower"] == "10 W"
    assert states["householdFromPvPower"] == "0 W"


def test_energy_overview_to_items_builds_battery_soc_item():
    items = energy_overview_to_items({"batterySoc": 54.444444})

    assert items == [
        {
            "name": "batterySoc",
            "label": "batterySoc",
            "state": "54.4 %",
            "type": "Number:Dimensionless",
            "editable": False,
            "category": "energy_overview",
            "stateDescription": {"pattern": "%.1f %%"},
        }
    ]


def test_energy_overview_to_legacy_items_builds_existing_power_names():
    items = energy_overview_to_legacy_items(
        {
            "production": 730,
            "feedIn": 501,
            "feedOut": 0,
            "householdConsumption": 229,
            "storagePowerIn": 0,
            "storagePowerOut": 0,
        },
        [
            {
                "id": "kiwigrid-location:standard:location-id",
                "thingType": {"id": "kiwigrid-location:standard"},
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
    assert states["kiwigrid_location_standard_location_id_harmonized_power_produced"] == "730 W"
    assert states["kiwigrid_location_standard_location_id_harmonized_power_out"] == "501 W"
    assert states["kiwigrid_location_standard_location_id_harmonized_power_consumed"] == "229 W"
    assert states["foxesshybrid_battery_serial_harmonized_power_in"] == "0 W"
    assert states["foxesshybrid_battery_serial_harmonized_power_out"] == "0 W"


def test_things_to_openhab_things_preserves_diagnostics_metadata():
    things = things_to_openhab_things(
        [
            {
                "id": "foxesshybrid:battery:123",
                "label": "Vision Battery",
                "thingType": {
                    "id": "foxesshybrid:battery",
                    "title": "Vision Battery",
                    "category": {"type": "STORAGES"},
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
            "UID": "energy-overview:standard:energy-overview",
            "uid": "energy-overview:standard:energy-overview",
            "label": "Energy Overview",
            "thingTypeUID": "energy-overview:standard",
            "thingTypeUid": "energy-overview:standard",
            "statusInfo": {"status": "ONLINE", "statusDetail": "NONE"},
            "properties": {
                "solarwatt.hemsConfigurator": "true",
                "solarwatt.energyOverview": "true",
                "thingTypeTitle": "Energy Overview",
                "thingTypeCategory": "ENERGY_OVERVIEW",
                "generatedLabel": "energymanager.local",
                "model": "energymanager.local",
            },
            "channels": [],
        },
        {
            "UID": "foxesshybrid:battery:123",
            "uid": "foxesshybrid:battery:123",
            "label": "Vision Battery",
            "thingTypeUID": "foxesshybrid:battery",
            "thingTypeUid": "foxesshybrid:battery",
            "statusInfo": {"status": "ONLINE", "statusDetail": "NONE"},
            "properties": {
                "serialNumber": "123",
                "thingTypeTitle": "Vision Battery",
                "thingTypeCategory": "STORAGES",
                "solarwatt.hemsConfigurator": "true",
            },
            "channels": [],
            "bridgeUID": "foxesshybrid:bridge:123",
            "bridgeUid": "foxesshybrid:bridge:123",
        }
    ]
    assert is_hems_thing(things[0])
    assert is_energy_overview_thing(things[0])
    assert is_hems_thing(things[1])


def test_item_names_to_thing_uids_maps_legacy_hems_items_by_prefix():
    item_to_thing_uid = item_names_to_thing_uids(
        [
            "production",
            "feedIn",
            "hems_flow_batteryPower",
            "hems_plug_15922327_c7d9_4fb9_ba65_9073bb627993_today_workin",
            "kiwigrid_location_standard_location_id_harmonized_power_consumed",
            "foxesshybrid_battery_serial_harmonized_power_out",
            "unknown_prefix_power",
        ],
        [
            {"UID": "energy-overview:standard:energy-overview"},
            {"UID": "15922327-c7d9-4fb9-ba65-9073bb627993"},
            {"UID": "kiwigrid-location:standard:location-id"},
            {"UID": "foxesshybrid:battery:serial"},
        ],
    )

    assert item_to_thing_uid == {
        "production": "energy-overview:standard:energy-overview",
        "feedIn": "energy-overview:standard:energy-overview",
        "hems_flow_batteryPower": KIWIGRID_FLOW_THING_UID,
        "hems_plug_15922327_c7d9_4fb9_ba65_9073bb627993_today_workin": (
            "15922327-c7d9-4fb9-ba65-9073bb627993"
        ),
        "kiwigrid_location_standard_location_id_harmonized_power_consumed": (
            "kiwigrid-location:standard:location-id"
        ),
        "foxesshybrid_battery_serial_harmonized_power_out": (
            "foxesshybrid:battery:serial"
        ),
    }


def test_kiwigrid_flow_thing_uses_hems_v11_device_model():
    thing = kiwigrid_flow_thing()

    assert thing["label"] == "KiwiGrid Flow"
    assert thing["properties"]["generatedLabel"] == "KiwiGrid HEMS v11"
    assert thing["properties"]["model"] == "KiwiGrid HEMS v11"
