from __future__ import annotations

import asyncio

from .module_loader import load_component_module

hems_client = load_component_module("hems_client")
KiwiGridHEMSClient = hems_client.KiwiGridHEMSClient
consumers_endpoint_to_items = hems_client.consumers_endpoint_to_items
energy_flow_endpoint_to_items = hems_client.energy_flow_endpoint_to_items
hems_payloads_to_items = hems_client.hems_payloads_to_items
hems_payloads_to_things = hems_client.hems_payloads_to_things


BATTERY_ID = "9c319824-bda6-4bbd-ac20-764dc1cfa34c"
EVSTATION_ID = "8695a754-d66c-430c-9fa6-374bac0965b3"
PV_ID = "95c5e9fb-e3d1-42b7-9a03-fd024ca58b9e"
GRID_METER_ID = "e34b5f52-bf2a-43b5-a2fb-caf2ed624624"
ANALYTICS_PRODUCTION_PAYLOAD = {
    "timeseries": [
        {
            "name": "PowerProduced",
            "aggregated": 60237,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~PowerProduced",
            "unit": "WATT",
            "values": {
                "2026-07-03T20:05+02:00": 445,
                "2026-07-03T20:10+02:00": 381,
            },
        },
        {
            "name": "PowerOut",
            "aggregated": 61111,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~PowerOut",
            "unit": "WATT",
            "values": {"2026-07-03T20:10+02:00": 6},
        },
        {
            "name": "PowerBuffered",
            "aggregated": 3895,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~PowerBuffered",
            "unit": "WATT",
            "values": {"2026-07-03T20:10+02:00": 0},
        },
        {
            "name": "PowerACOut",
            "aggregated": 60237,
            "guid": PV_ID,
            "id": f"{PV_ID}~PowerACOut",
            "unit": "WATT",
            "values": {"2026-07-03T20:10+02:00": 381},
        },
    ],
    "resolution": "PT5M",
    "time_zone": "Europe/Berlin",
    "devices": [{"id": PV_ID, "name": "PV Anlage", "type": "PV"}],
}
ANALYTICS_STORAGE_PAYLOAD = {
    "timeseries": [
        {
            "name": "PowerACIn",
            "aggregated": 5959,
            "guid": BATTERY_ID,
            "id": f"{BATTERY_ID}~PowerACIn",
            "unit": "WATT",
            "values": {
                "2026-07-03T20:05+02:00": 0,
                "2026-07-03T20:10+02:00": 0,
                "2026-07-03T23:55+02:00": None,
            },
        },
        {
            "name": "PowerACOut",
            "aggregated": 6800,
            "guid": BATTERY_ID,
            "id": f"{BATTERY_ID}~PowerACOut",
            "unit": "WATT",
            "values": {
                "2026-07-03T20:05+02:00": 0,
                "2026-07-03T20:10+02:00": 0,
            },
        },
        {
            "name": "PowerBuffered",
            "aggregated": 3895,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~PowerBuffered",
            "unit": "WATT",
            "values": {
                "2026-07-03T20:05+02:00": 445,
                "2026-07-03T20:10+02:00": 2618,
            },
        },
        {
            "name": "PowerReleased",
            "aggregated": 6761,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~PowerReleased",
            "unit": "WATT",
            "values": {
                "2026-07-03T20:05+02:00": 0,
                "2026-07-03T20:10+02:00": 0,
            },
        },
        {
            "name": "StateOfCharge",
            "guid": BATTERY_ID,
            "id": f"{BATTERY_ID}~StateOfCharge",
            "unit": "PERCENT",
            "values": {
                "2026-07-03T23:50+02:00": 39,
                "2026-07-03T23:55+02:00": 39,
            },
        },
    ],
    "resolution": "PT5M",
    "time_zone": "Europe/Berlin",
    "devices": [
        {
            "id": BATTERY_ID,
            "name": "SOLARWATT Battery vision three",
            "state_device": "OK",
            "type": "BATTERY",
        }
    ],
}
ANALYTICS_INDEPENDENCE_PAYLOAD = {
    "timeseries": [
        {
            "name": "Autarky",
            "aggregated": 100,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~Autarky",
            "unit": "PERCENT",
            "values": {
                "2026-07-04T07:00+02:00": 100,
                "2026-07-04T08:00+02:00": 99,
            },
        },
        {
            "name": "SelfConsumptionRate",
            "aggregated": 100,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~SelfConsumptionRate",
            "unit": "PERCENT",
            "values": {
                "2026-07-04T07:00+02:00": 100,
                "2026-07-04T08:00+02:00": 100,
            },
        },
    ],
    "resolution": "PT1H",
    "time_zone": "Europe/Berlin",
}
ANALYTICS_STORAGE_MONTH_PAYLOAD = {
    "timeseries": [
        {
            "name": "WorkACIn",
            "aggregated": 64691,
            "guid": BATTERY_ID,
            "id": f"{BATTERY_ID}~WorkACIn",
            "unit": "WATTHOUR",
            "values": {"2026-07-08T00:00+02:00": 10596},
        },
        {
            "name": "WorkReleased",
            "aggregated": 57093,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkReleased",
            "unit": "WATTHOUR",
            "values": {"2026-07-08T00:00+02:00": 7267},
        },
    ],
    "resolution": "P1D",
    "time_zone": "Europe/Berlin",
    "devices": [
        {"id": BATTERY_ID, "name": "SOLARWATT Battery vision three", "type": "BATTERY"}
    ],
}
ANALYTICS_STORAGE_YEAR_PAYLOAD = {
    "timeseries": [
        {
            "name": "WorkACIn",
            "aggregated": 1072447,
            "guid": BATTERY_ID,
            "id": f"{BATTERY_ID}~WorkACIn",
            "unit": "WATTHOUR",
            "values": {"2026-07-01T00:00+02:00": 64691},
        },
        {
            "name": "WorkBuffered",
            "aggregated": 1064067,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkBuffered",
            "unit": "WATTHOUR",
            "values": {"2026-07-01T00:00+02:00": 62551},
        },
    ],
    "resolution": "P1M",
    "time_zone": "Europe/Berlin",
    "devices": [
        {"id": BATTERY_ID, "name": "SOLARWATT Battery vision three", "type": "BATTERY"}
    ],
}
ANALYTICS_INDEPENDENCE_MONTH_PAYLOAD = {
    "timeseries": [
        {
            "name": "Autarky",
            "aggregated": 98,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~Autarky",
            "unit": "PERCENT",
            "values": {"2026-07-08T00:00+02:00": 93},
        },
        {
            "name": "SelfConsumptionRate",
            "aggregated": 49,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~SelfConsumptionRate",
            "unit": "PERCENT",
            "values": {"2026-07-08T00:00+02:00": 65},
        },
    ],
    "resolution": "P1D",
    "time_zone": "Europe/Berlin",
}
ANALYTICS_INDEPENDENCE_YEAR_PAYLOAD = {
    "timeseries": [
        {
            "name": "Autarky",
            "aggregated": 68,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~Autarky",
            "unit": "PERCENT",
            "values": {"2026-07-01T00:00+02:00": 98},
        },
        {
            "name": "SelfConsumptionRate",
            "aggregated": 28,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~SelfConsumptionRate",
            "unit": "PERCENT",
            "values": {"2026-07-01T00:00+02:00": 49},
        },
    ],
    "resolution": "P1M",
    "time_zone": "Europe/Berlin",
}
ANALYTICS_CONSUMPTION_PAYLOAD = {
    "timeseries": [
        {
            "name": "PowerConsumed",
            "aggregated": 12036,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~PowerConsumed",
            "unit": "WATT",
            "values": {
                "2026-07-03T23:05+02:00": 688,
                "2026-07-03T23:10+02:00": 659,
                "2026-07-03T23:15+02:00": None,
            },
        },
        {
            "name": "PowerIn",
            "aggregated": 404,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~PowerIn",
            "unit": "WATT",
            "values": {
                "2026-07-03T23:05+02:00": 13,
                "2026-07-03T23:10+02:00": 3,
                "2026-07-03T23:15+02:00": None,
            },
        },
    ],
    "resolution": "PT5M",
    "time_zone": "Europe/Berlin",
    "devices": [
        {
            "id": "8695a754-d66c-430c-9fa6-374bac0965b3",
            "name": "Keba P30 PV-Edition",
            "state_device": "OK",
            "type": "EV_STATION",
        }
    ],
}
ANALYTICS_FINANCE_PAYLOAD = {
    "timeseries": [
        {
            "name": "Revenue",
            "aggregated": 1234,
            "unit": "CENT",
            "values": {
                "2026-07-04T10:00+02:00": 11,
                "2026-07-04T11:00+02:00": 12,
            },
        }
    ],
    "resolution": "PT1H",
    "time_zone": "Europe/Berlin",
}
ANALYTICS_FINANCE_MONTH_PAYLOAD = {
    "timeseries": [
        {
            "name": "cost",
            "aggregated": 0.44,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~cost",
            "unit": "CURRENCY",
            "values": {"2026-07-01T00:00+02:00": 0.44},
        },
        {
            "name": "profit",
            "aggregated": 23.31,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~profit",
            "unit": "CURRENCY",
            "values": {"2026-07-01T00:00+02:00": 23.31},
        },
    ],
    "resolution": "P1D",
    "time_zone": "Europe/Berlin",
}
ANALYTICS_FINANCE_YEAR_PAYLOAD = {
    "timeseries": [
        {
            "name": "cost",
            "aggregated": 11.23,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~cost",
            "unit": "CURRENCY",
            "values": {"2026-07-01T00:00+02:00": 0.44},
        },
        {
            "name": "balance",
            "aggregated": 684.87,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~balance",
            "unit": "CURRENCY",
            "values": {"2026-07-01T00:00+02:00": 22.87},
        },
    ],
    "resolution": "P1M",
    "time_zone": "Europe/Berlin",
}
ANALYTICS_CONSUMPTION_YEAR_PAYLOAD = {
    "timeseries": [
        {
            "name": "WorkConsumed",
            "aggregated": 4477421,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkConsumed",
            "unit": "WATTHOUR",
            "values": {"2026-01-01T00:00+01:00": 817066},
        },
        {
            "name": "WorkACIn",
            "aggregated": 2680271,
            "guid": EVSTATION_ID,
            "id": f"{EVSTATION_ID}~WorkACIn",
            "unit": "WATTHOUR",
            "values": {"2026-01-01T00:00+01:00": 533884},
        },
    ],
    "resolution": "P1M",
    "time_zone": "Europe/Berlin",
    "devices": [{"id": EVSTATION_ID, "name": "Keba P30 PV-Edition", "type": "EV_STATION"}],
}
ANALYTICS_CONSUMPTION_MONTH_PAYLOAD = {
    "timeseries": [
        {
            "name": "WorkConsumed",
            "aggregated": 83058,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkConsumed",
            "unit": "WATTHOUR",
            "values": {"2026-07-04T00:00+02:00": 18975},
        },
        {
            "name": "WorkACIn",
            "aggregated": 46874,
            "guid": EVSTATION_ID,
            "id": f"{EVSTATION_ID}~WorkACIn",
            "unit": "WATTHOUR",
            "values": {"2026-07-04T00:00+02:00": 5468},
        },
    ],
    "resolution": "P1D",
    "time_zone": "Europe/Berlin",
    "devices": [{"id": EVSTATION_ID, "name": "Keba P30 PV-Edition", "type": "EV_STATION"}],
}
ANALYTICS_CONSUMPTION_WORK_TODAY_PAYLOAD = {
    "timeseries": [
        {
            "name": "WorkConsumed",
            "aggregated": 37510,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkConsumed",
            "unit": "WATTHOUR",
            "values": {"2026-07-05T17:00+02:00": 647},
        },
        {
            "name": "WorkACIn",
            "aggregated": 25643,
            "guid": EVSTATION_ID,
            "id": f"{EVSTATION_ID}~WorkACIn",
            "unit": "WATTHOUR",
            "values": {"2026-07-05T17:00+02:00": 0},
        },
        {
            "name": "WorkIn",
            "aggregated": 123,
            "guid": "15922327-c7d9-4fb9-ba65-9073bb627993",
            "id": "15922327-c7d9-4fb9-ba65-9073bb627993~WorkIn",
            "unit": "WATTHOUR",
            "values": {"2026-07-05T17:00+02:00": 0},
        },
        {
            "name": "WorkIn",
            "aggregated": 456,
            "guid": "6b008e41-5453-416f-a842-a391bb7f106a",
            "id": "6b008e41-5453-416f-a842-a391bb7f106a~WorkIn",
            "unit": "WATTHOUR",
            "values": {"2026-07-05T17:00+02:00": 0},
        },
    ],
    "resolution": "PT1H",
    "time_zone": "Europe/Berlin",
    "devices": [
        {
            "id": EVSTATION_ID,
            "name": "Keba P30 PV-Edition",
            "state_device": "OK",
            "type": "EV_STATION",
        },
        {
            "id": "15922327-c7d9-4fb9-ba65-9073bb627993",
            "name": "myStrom (Waschmaschine)",
            "state_device": "OK",
            "type": "PLUG",
        },
        {
            "id": "6b008e41-5453-416f-a842-a391bb7f106a",
            "name": "myStrom (Wasserpumpe)",
            "state_device": "OK",
            "type": "PLUG",
        },
    ],
}
ANALYTICS_PRODUCTION_YEAR_PAYLOAD = {
    "timeseries": [
        {
            "name": "WorkProduced",
            "aggregated": 11338531,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkProduced",
            "unit": "WATTHOUR",
            "values": {"2026-01-01T00:00+01:00": 458532},
        },
        {
            "name": "WorkOut",
            "aggregated": 8405903,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkOut",
            "unit": "WATTHOUR",
            "values": {"2026-01-01T00:00+01:00": 228644},
        },
        {
            "name": "WorkBuffered",
            "aggregated": 1046393,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkBuffered",
            "unit": "WATTHOUR",
            "values": {"2026-01-01T00:00+01:00": 102237},
        },
        {
            "name": "WorkACOut",
            "aggregated": 11338531,
            "guid": PV_ID,
            "id": f"{PV_ID}~WorkACOut",
            "unit": "WATTHOUR",
            "values": {"2026-01-01T00:00+01:00": 458532},
        },
    ],
    "resolution": "P1M",
    "time_zone": "Europe/Berlin",
    "devices": [{"id": PV_ID, "name": "PV Anlage", "type": "PV"}],
}
ANALYTICS_PRODUCTION_MONTH_PAYLOAD = {
    "timeseries": [
        {
            "name": "WorkProduced",
            "aggregated": 203998,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkProduced",
            "unit": "WATTHOUR",
            "values": {"2026-07-04T00:00+02:00": 37728},
        },
        {
            "name": "WorkOut",
            "aggregated": 211607,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkOut",
            "unit": "WATTHOUR",
            "values": {"2026-07-04T00:00+02:00": 14798},
        },
        {
            "name": "WorkBuffered",
            "aggregated": 44878,
            "guid": GRID_METER_ID,
            "id": f"{GRID_METER_ID}~WorkBuffered",
            "unit": "WATTHOUR",
            "values": {"2026-07-04T00:00+02:00": 11163},
        },
        {
            "name": "WorkACOut",
            "aggregated": 203998,
            "guid": PV_ID,
            "id": f"{PV_ID}~WorkACOut",
            "unit": "WATTHOUR",
            "values": {"2026-07-04T00:00+02:00": 37728},
        },
    ],
    "resolution": "P1D",
    "time_zone": "Europe/Berlin",
    "devices": [{"id": PV_ID, "name": "PV Anlage", "type": "PV"}],
}


class _FakeContextResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    async def text(self):
        return ""


class _FakeContextSession:
    def get(self, *args, **kwargs):
        return _FakeContextResponse()


def test_hems_context_empty_body_returns_empty_context():
    client = KiwiGridHEMSClient(_FakeContextSession())

    assert asyncio.run(client._async_fetch_context()) == {}


def test_hems_payloads_to_items_maps_battery_measurements_without_metadata_sensors():
    items = hems_payloads_to_items(
        batteries=[
            {
                "id": BATTERY_ID,
                "name": "SOLARWATT Battery vision three",
                "type": "BATTERY",
                "manufacturer": "SOLARWATT",
                "model_code": "Battery vision three",
                "serial_number": "BAT-123",
                "firmware": "1.2.3",
                "state_device": "OK",
                "configured_in_location": True,
                "state_of_charge": 0.82,
                "backup_active": False,
                "work_capacity": 5120,
            }
        ],
    )

    states = {item["name"]: item["state"] for item in items}

    assert f"hems_battery_{BATTERY_ID.replace('-', '_')}_state_of_charge" in states
    assert states[f"hems_battery_{BATTERY_ID.replace('-', '_')}_state_of_charge"] == "82 %"
    assert states[f"hems_battery_{BATTERY_ID.replace('-', '_')}_backup_active"] == "false"
    assert states[f"hems_battery_{BATTERY_ID.replace('-', '_')}_work_capacity"] == "5120 Wh"
    assert next(
        item
        for item in items
        if item["name"] == f"hems_battery_{BATTERY_ID.replace('-', '_')}_type"
    )["entityCategory"] == "diagnostic"
    assert next(
        item
        for item in items
        if item["name"] == f"hems_battery_{BATTERY_ID.replace('-', '_')}_state_device"
    )["entityCategory"] == "diagnostic"
    assert not any(item["name"].endswith("_name") for item in items)
    assert not any(item["name"].endswith("_manufacturer") for item in items)
    assert not any(item["name"].endswith("_serial_number") for item in items)
    assert not any(item["name"].endswith("_firmware") for item in items)


def test_hems_payloads_to_items_maps_energy_flow_to_kiwigrid_flow_items():
    items = hems_payloads_to_items(
        energy_flow={
            "consumption": {"in": 949, "direct_consumption": 0},
            "grid": {"in": 0, "out": 0, "balance": 0},
            "pv": {"out": 0},
            "battery": {
                "in": 0,
                "out": 949,
                "in_from_grid": 0,
                "out_to_grid": 6,
                "soc": 0.5444444444444444,
                "balance": -949,
            },
            "ev": {"in": 0, "out": 0, "balance": 0},
        }
    )

    states = {item["name"]: item["state"] for item in items}
    assert states["hems_flow_consumption_in"] == "949 W"
    assert states["hems_flow_consumption_direct_consumption"] == "0 W"
    assert states["hems_flow_grid_in"] == "0 W"
    assert states["hems_flow_grid_out"] == "0 W"
    assert states["hems_flow_pv_out"] == "0 W"
    assert states["hems_flow_battery_in"] == "0 W"
    assert states["hems_flow_battery_out"] == "949 W"
    assert states["hems_flow_battery_out_to_grid"] == "6 W"
    assert states["hems_flow_battery_soc"] == "54.4 %"


def test_hems_payloads_to_items_maps_energy_flow_grid_import_and_battery_discharge():
    items = hems_payloads_to_items(
        energy_flow={
            "consumption": {"in": 1041, "direct_consumption": 0},
            "grid": {"in": 11, "out": 0, "balance": 11},
            "pv": {"out": 0},
            "battery": {
                "in": 0,
                "out": 1030,
                "in_from_grid": 0,
                "out_to_grid": 0,
                "soc": 0.5,
                "balance": -1030,
            },
            "ev": {"in": 0, "out": 0, "balance": 0},
        }
    )

    states = {item["name"]: item["state"] for item in items}
    assert states["hems_flow_consumption_in"] == "1041 W"
    assert states["hems_flow_grid_in"] == "11 W"
    assert states["hems_flow_grid_out"] == "0 W"
    assert states["hems_flow_grid_balance"] == "11 W"
    assert states["hems_flow_battery_out"] == "1030 W"
    assert states["hems_flow_battery_balance"] == "-1030 W"
    assert states["hems_flow_battery_soc"] == "50 %"


def test_energy_flow_endpoint_to_items_maps_current_hems_payload_as_json_paths():
    items = energy_flow_endpoint_to_items(
        {
            "consumption": {
                "in": 499,
                "direct_consumption": 0,
                "devices": [{"id": GRID_METER_ID}],
            },
            "grid": {
                "in": 0,
                "out": 0,
                "balance": 0,
                "devices": [{"id": GRID_METER_ID}],
            },
            "pv": {"out": 0, "devices": [{"id": PV_ID, "out": 0}]},
            "battery": {
                "in": 0,
                "out": 499,
                "in_from_grid": 0,
                "out_to_grid": 2,
                "soc": 0.34444444444444444,
                "balance": -499,
                "devices": [
                    {
                        "id": BATTERY_ID,
                        "in": 0,
                        "out": 490,
                        "soc": 0.34444444444444444,
                        "balance": -490,
                    }
                ],
            },
            "ev": {
                "in": 0,
                "out": 0,
                "balance": 0,
                "bidirectional": False,
                "devices": [{"id": EVSTATION_ID, "in": 0}],
            },
        }
    )

    states = {item["name"]: item["state"] for item in items}
    assert states["hems_flow_consumption_in"] == "499 W"
    assert states["hems_flow_consumption_direct_consumption"] == "0 W"
    assert states["hems_flow_grid_in"] == "0 W"
    assert states["hems_flow_grid_out"] == "0 W"
    assert states["hems_flow_grid_balance"] == "0 W"
    assert states["hems_flow_pv_out"] == "0 W"
    assert states["hems_flow_battery_in"] == "0 W"
    assert states["hems_flow_battery_out"] == "499 W"
    assert states["hems_flow_battery_in_from_grid"] == "0 W"
    assert states["hems_flow_battery_out_to_grid"] == "2 W"
    assert states["hems_flow_battery_soc"] == "34.4 %"
    assert states["hems_flow_battery_balance"] == "-499 W"
    assert states["hems_flow_ev_in"] == "0 W"
    assert states["hems_flow_ev_out"] == "0 W"
    assert states["hems_flow_ev_balance"] == "0 W"
    assert states["hems_flow_ev_bidirectional"] == "false"
    assert not any(name.startswith("hems_flow_device_") for name in states)


def test_hems_payloads_to_items_uses_device_names_for_flow_device_values():
    items = hems_payloads_to_items(
        batteries=[{"id": BATTERY_ID, "name": "SOLARWATT Battery vision three"}],
        pv_plants=[{"id": PV_ID, "name": "PV Anlage"}],
        evstations=[{"id": EVSTATION_ID, "name": "Keba P30 PV-Edition"}],
        energy_flow={
            "pv": {"out": 0, "devices": [{"id": PV_ID, "out": 0}]},
            "battery": {
                "out": 499,
                "devices": [{"id": BATTERY_ID, "out": 490, "balance": -490}],
            },
            "ev": {"in": 0, "devices": [{"id": EVSTATION_ID, "in": 0}]},
        },
    )

    states = {item["name"]: item["state"] for item in items}
    assert states["hems_flow_solarwatt_battery_vision_three_out"] == "490 W"
    assert states["hems_flow_solarwatt_battery_vision_three_balance"] == "-490 W"
    assert states["hems_flow_pv_anlage_out"] == "0 W"
    assert states["hems_flow_keba_p30_pv_edition_in"] == "0 W"


def test_hems_payloads_to_items_uses_device_endpoint_names_for_flow_device_values():
    items = hems_payloads_to_items(
        devices=[
            {"id": BATTERY_ID, "name": "SOLARWATT Battery vision three"},
            {"id": PV_ID, "name": "PV Anlage"},
            {"id": EVSTATION_ID, "name": "Keba P30 PV-Edition"},
        ],
        energy_flow={
            "pv": {"out": 0, "devices": [{"id": PV_ID, "out": 0}]},
            "battery": {
                "out": 499,
                "devices": [{"id": BATTERY_ID, "out": 490, "balance": -490}],
            },
            "ev": {"in": 0, "devices": [{"id": EVSTATION_ID, "in": 0}]},
        },
    )

    states = {item["name"]: item["state"] for item in items}
    assert "hems_flow_device_9c319824_bda6_4bbd_ac20_764dc1cfa34c_out" not in states
    assert states["hems_flow_solarwatt_battery_vision_three_out"] == "490 W"
    assert states["hems_flow_solarwatt_battery_vision_three_balance"] == "-490 W"
    assert states["hems_flow_pv_anlage_out"] == "0 W"
    assert states["hems_flow_keba_p30_pv_edition_in"] == "0 W"


def test_hems_payloads_to_items_uses_optimization_names_for_flow_device_values():
    items = hems_payloads_to_items(
        device_optimizations=[
            {"id": BATTERY_ID, "name": "SOLARWATT Battery vision three"},
            {"id": EVSTATION_ID, "name": "Keba P30 PV-Edition"},
        ],
        energy_flow={
            "battery": {
                "out": 499,
                "devices": [{"id": BATTERY_ID, "out": 490, "balance": -490}],
            },
            "ev": {"in": 0, "devices": [{"id": EVSTATION_ID, "in": 0}]},
        },
    )

    states = {item["name"]: item["state"] for item in items}
    assert "hems_flow_device_9c319824_bda6_4bbd_ac20_764dc1cfa34c_out" not in states
    assert states["hems_flow_solarwatt_battery_vision_three_out"] == "490 W"
    assert states["hems_flow_keba_p30_pv_edition_in"] == "0 W"


def test_consumers_endpoint_to_items_maps_live_consumption_to_flow_items():
    items = consumers_endpoint_to_items(
        [
            {
                "id": "15922327-c7d9-4fb9-ba65-9073bb627993",
                "name": "myStrom (Waschmaschine)",
                "consumption": 1.68,
            },
            {
                "id": EVSTATION_ID,
                "name": "Keba P30 PV-Edition",
                "consumption": 0.0,
            },
            {
                "id": "6b008e41-5453-416f-a842-a391bb7f106a",
                "name": "myStrom (Wasserpumpe)",
                "consumption": 0.0,
            },
        ]
    )

    states = {item["name"]: item["state"] for item in items}
    assert states["hems_flow_mystrom_waschmaschine_consumption"] == "1.68 W"
    assert states["hems_flow_keba_p30_pv_edition_consumption"] == "0 W"
    assert states["hems_flow_mystrom_wasserpumpe_consumption"] == "0 W"
    assert {item["category"] for item in items} == {"kiwigrid_flow"}


def test_hems_payloads_to_items_maps_home_consumption_consumers_to_flow_items():
    items = hems_payloads_to_items(
        home_consumption_consumers=[
            {
                "id": "15922327-c7d9-4fb9-ba65-9073bb627993",
                "name": "myStrom (Waschmaschine)",
                "consumption": 1.68,
            }
        ]
    )

    states = {item["name"]: item["state"] for item in items}
    assert states["hems_flow_mystrom_waschmaschine_consumption"] == "1.68 W"


def test_async_get_energy_flow_uses_live_endpoint_without_query_parameters():
    class FakeClient(KiwiGridHEMSClient):
        def __init__(self):
            super().__init__(session=None, username="user", password="pass")
            self.requested_path = None

        async def _async_get_json(self, path, *, where):
            self.requested_path = path
            return {}

    client = FakeClient()

    asyncio.run(client.async_get_energy_flow())

    assert client.requested_path == "/energy-flow"


def test_async_get_home_consumption_consumers_uses_live_endpoint_without_query_parameters():
    class FakeClient(KiwiGridHEMSClient):
        def __init__(self):
            super().__init__(session=None, username="user", password="pass")
            self.requested_path = None

        async def _async_get_json(self, path, *, where):
            self.requested_path = path
            return []

    client = FakeClient()

    asyncio.run(client.async_get_home_consumption_consumers())

    assert client.requested_path == "/home/consumption/consumers"


def test_hems_payloads_to_items_skips_generic_device_when_specific_endpoint_exists():
    items = hems_payloads_to_items(
        batteries=[
            {
                "id": BATTERY_ID,
                "name": "SOLARWATT Battery vision three",
                "state_of_charge": 0.4,
            }
        ],
        devices=[
            {
                "id": BATTERY_ID,
                "name": "SOLARWATT Battery vision three",
                "type": "BATTERY",
                "mode": "AUTO",
            }
        ],
    )

    assert any(item["name"].startswith("hems_battery_") for item in items)
    assert not any(item["name"].startswith("hems_device_") for item in items)


def test_hems_payloads_merge_device_optimization_metadata():
    items = hems_payloads_to_items(
        evstations=[
            {
                "id": EVSTATION_ID,
                "name": "Keba P30 PV-Edition",
                "type": "EV_STATION",
                "state_device": "OK",
            }
        ],
        device_optimizations=[
            {
                "id": EVSTATION_ID,
                "name": "Keba P30 PV-Edition",
                "supported_optimization_modes": [
                    "NOT_OPTIMIZED",
                    "PV_EXCESS",
                    "DEPARTURE_TIME",
                ],
                "supports_switching": True,
                "switch_state": "OFF",
                "config": {"optimization_mode": "NOT_OPTIMIZED"},
            }
        ],
    )
    states = {item["name"]: item["state"] for item in items}
    prefix = f"hems_evstation_{EVSTATION_ID.replace('-', '_')}"

    assert states[f"{prefix}_optimization_mode"] == "NOT_OPTIMIZED"
    assert states[f"{prefix}_supports_switching"] == "true"
    assert states[f"{prefix}_switch_state"] == "OFF"

    things = hems_payloads_to_things(
        evstations=[
            {
                "id": EVSTATION_ID,
                "name": "Keba P30 PV-Edition",
                "type": "EV_STATION",
                "state_device": "OK",
            }
        ],
        device_optimizations=[
            {
                "id": EVSTATION_ID,
                "name": "Keba P30 PV-Edition",
                "supported_optimization_modes": [
                    "NOT_OPTIMIZED",
                    "PV_EXCESS",
                    "DEPARTURE_TIME",
                ],
                "supports_switching": True,
                "switch_state": "OFF",
                "config": {"optimization_mode": "NOT_OPTIMIZED"},
            }
        ],
    )
    props = things[0]["properties"]

    assert props["optimizationMode"] == "NOT_OPTIMIZED"
    assert props["optimizationSupportsSwitching"] == "True"
    assert props["optimizationSupportedModes"] == "NOT_OPTIMIZED,PV_EXCESS,DEPARTURE_TIME"


def test_hems_payloads_to_things_uses_payload_name_and_device_metadata():
    things = hems_payloads_to_things(
        pv_plants=[
            {
                "id": PV_ID,
                "name": "SMA Sunny Tripower 20000TL",
                "type": "INVERTER",
                "manufacturer": "SMA",
                "model_code": "Sunny Tripower 20000TL",
                "serial_number": "1901399614",
                "firmware": "4.1.0",
                "state_device": "OK",
                "power_installed_peak": 20000,
            }
        ],
    )

    assert len(things) == 1
    thing = things[0]

    assert thing["UID"] == PV_ID
    assert thing["label"] == "SMA Sunny Tripower 20000TL"
    assert thing["thingTypeUID"] == "kiwigrid-hems:pv_plant"
    assert thing["statusInfo"]["status"] == "ONLINE"
    assert thing["properties"] == {
        "thingTypeTitle": "KiwiGrid HEMS PV Plant",
        "thingTypeCategory": "KIWIGRID_HEMS",
        "kiwigridEndpoint": "/v11/pv-plant",
        "kiwigridKind": "pv_plant",
        "generatedLabel": "Sunny Tripower 20000TL",
        "vendor": "SMA",
        "manufacturer": "SMA",
        "serialNumber": "1901399614",
        "firmware": "4.1.0",
        "model": "Sunny Tripower 20000TL",
        "identifier": PV_ID,
    }
    assert [channel["linkedItems"][0] for channel in thing["channels"]] == [
        f"hems_pv_plant_{PV_ID.replace('-', '_')}_type",
        f"hems_pv_plant_{PV_ID.replace('-', '_')}_state_device",
        f"hems_pv_plant_{PV_ID.replace('-', '_')}_power_installed_peak",
    ]


def test_hems_payloads_to_things_ignores_numeric_only_model_code():
    plug_id = "15922327-c7d9-4fb9-ba65-9073bb627993"
    things = hems_payloads_to_things(
        plugs=[
            {
                "id": plug_id,
                "name": "myStrom (Waschmaschine)",
                "type": "PLUG",
                "manufacturer": "myStrom AG",
                "model_code": "107",
                "firmware": "4.0.14",
                "state_device": "OK",
            }
        ],
    )

    props = things[0]["properties"]

    assert props["generatedLabel"] == "PLUG"
    assert props["model"] == "PLUG"
    assert props["manufacturer"] == "myStrom AG"
    assert "107" not in props.values()


def test_hems_payloads_to_items_maps_analytics_production_summary():
    items = hems_payloads_to_items(analytics_production=ANALYTICS_PRODUCTION_PAYLOAD)
    states = {item["name"]: item["state"] for item in items}

    assert states["hems_analytics_production_today_production_powerproduced"] == "60237 Wh"
    assert states["hems_analytics_production_today_production_powerproduced_latest"] == "381 W"
    assert states["hems_analytics_production_today_production_powerout"] == "61111 Wh"
    assert states["hems_analytics_production_today_production_powerbuffered"] == "3895 Wh"
    assert f"hems_pv_plant_{PV_ID.replace('-', '_')}_today_production_poweracout" not in states
    assert f"hems_pv_plant_{PV_ID.replace('-', '_')}_today_poweracout" not in states


def test_hems_payloads_to_things_adds_analytics_production_channels_to_kiwigrid_hems():
    things = hems_payloads_to_things(analytics_production=ANALYTICS_PRODUCTION_PAYLOAD)

    assert len(things) == 1
    thing = things[0]

    assert thing["UID"] == "kiwigrid-hems"
    assert thing["label"] == "KiwiGrid Stats"
    assert thing["thingTypeUID"] == "kiwigrid-hems:analytics_production"
    assert thing["properties"]["kiwigridEndpoint"] == "/v11/analytics/production"
    assert thing["properties"]["generatedLabel"] == "KiwiGrid HEMS v11"
    assert thing["properties"]["model"] == "KiwiGrid HEMS v11"
    assert "identifier" not in thing["properties"]
    assert "serialNumber" not in thing["properties"]
    assert "hems_analytics_production_today_production_powerproduced" in {
        channel["linkedItems"][0] for channel in thing["channels"]
    }


def test_hems_payloads_to_items_maps_analytics_storage_summary():
    items = hems_payloads_to_items(analytics_storage=ANALYTICS_STORAGE_PAYLOAD)
    states = {item["name"]: item["state"] for item in items}

    assert states["hems_analytics_storage_today_storage_poweracin"] == "5959 Wh"
    assert states["hems_analytics_storage_today_storage_poweracin_latest"] == "0 W"
    assert states["hems_analytics_storage_today_storage_poweracout"] == "6800 Wh"
    assert states["hems_analytics_storage_today_storage_powerbuffered"] == "3895 Wh"
    assert states["hems_analytics_storage_today_storage_powerbuffered_latest"] == "2618 W"
    assert states["hems_analytics_storage_today_storage_powerreleased"] == "6761 Wh"
    assert states["hems_analytics_storage_today_storage_powerreleased_latest"] == "0 W"
    assert states["hems_analytics_storage_today_storage_stateofcharge_latest"] == "39 %"
    assert f"hems_battery_{BATTERY_ID.replace('-', '_')}_today_storage_poweracin" not in states
    assert f"hems_battery_{BATTERY_ID.replace('-', '_')}_today_poweracin" not in states
    assert "hems_analytics_storage_today_storage_stateofcharge" not in states


def test_hems_payloads_to_things_adds_analytics_storage_channels_to_kiwigrid_hems():
    things = hems_payloads_to_things(analytics_storage=ANALYTICS_STORAGE_PAYLOAD)

    assert len(things) == 1
    thing = things[0]

    assert thing["UID"] == "kiwigrid-hems"
    assert thing["label"] == "KiwiGrid Stats"
    assert thing["thingTypeUID"] == "kiwigrid-hems:analytics_storage"
    assert thing["properties"]["kiwigridEndpoint"] == "/v11/analytics/storage"
    assert thing["properties"]["generatedLabel"] == "KiwiGrid HEMS v11"
    assert thing["properties"]["model"] == "KiwiGrid HEMS v11"
    assert "identifier" not in thing["properties"]
    linked_items = {channel["linkedItems"][0] for channel in thing["channels"]}
    assert "hems_analytics_storage_today_storage_powerbuffered" in linked_items
    assert "hems_analytics_storage_today_storage_poweracin" in linked_items


def test_hems_payloads_to_items_maps_analytics_independence_summary():
    items = hems_payloads_to_items(analytics_independence=ANALYTICS_INDEPENDENCE_PAYLOAD)
    states = {item["name"]: item["state"] for item in items}

    assert states["hems_analytics_independence_today_independence_autarky"] == "100 %"
    assert states["hems_analytics_independence_today_independence_autarky_latest"] == "99 %"
    assert (
        states["hems_analytics_independence_today_independence_selfconsumptionrate"]
        == "100 %"
    )
    assert (
        states[
            "hems_analytics_independence_today_independence_selfconsumptionrate_latest"
        ]
        == "100 %"
    )


def test_hems_payloads_to_things_adds_analytics_independence_channels_to_kiwigrid_hems():
    things = hems_payloads_to_things(analytics_independence=ANALYTICS_INDEPENDENCE_PAYLOAD)

    assert len(things) == 1
    thing = things[0]

    assert thing["UID"] == "kiwigrid-hems"
    assert thing["label"] == "KiwiGrid Stats"
    assert thing["thingTypeUID"] == "kiwigrid-hems:analytics_independence"
    assert thing["properties"]["kiwigridEndpoint"] == "/v11/analytics/independence"
    assert thing["properties"]["generatedLabel"] == "KiwiGrid HEMS v11"
    assert thing["properties"]["model"] == "KiwiGrid HEMS v11"
    assert "identifier" not in thing["properties"]
    assert "hems_analytics_independence_today_independence_autarky" in {
        channel["linkedItems"][0] for channel in thing["channels"]
    }


def test_hems_payloads_to_items_maps_analytics_consumption_summary():
    items = hems_payloads_to_items(analytics_consumption=ANALYTICS_CONSUMPTION_PAYLOAD)
    states = {item["name"]: item["state"] for item in items}

    assert states["hems_analytics_consumption_today_consumption_powerconsumed"] == "12036 Wh"
    assert (
        states["hems_analytics_consumption_today_consumption_powerconsumed_latest"]
        == "659 W"
    )
    assert states["hems_analytics_consumption_today_consumption_powerin"] == "404 Wh"
    assert states["hems_analytics_consumption_today_consumption_powerin_latest"] == "3 W"


def test_hems_payloads_to_things_adds_analytics_consumption_channels_to_kiwigrid_hems():
    things = hems_payloads_to_things(
        analytics_consumption=ANALYTICS_CONSUMPTION_PAYLOAD,
    )

    assert len(things) == 1
    thing = things[0]

    assert thing["UID"] == "kiwigrid-hems"
    assert thing["label"] == "KiwiGrid Stats"
    assert thing["thingTypeUID"] == "kiwigrid-hems:analytics_consumption"
    assert thing["properties"]["kiwigridEndpoint"] == "/v11/analytics/consumption"
    assert "hems_analytics_consumption_today_consumption_powerconsumed" in {
        channel["linkedItems"][0] for channel in thing["channels"]
    }


def test_hems_payloads_to_items_maps_analytics_finance_summary():
    items = hems_payloads_to_items(
        analytics_finance=ANALYTICS_FINANCE_PAYLOAD,
        user_profile={"currency": "EUR"},
    )
    states = {item["name"]: item["state"] for item in items}

    assert states["hems_analytics_finance_today_finance_revenue"] == "12.34 EUR"
    assert states["hems_analytics_finance_today_finance_revenue_latest"] == "0.12 EUR"


def test_hems_payloads_to_items_maps_analytics_finance_month_and_year_payloads():
    items = hems_payloads_to_items(
        analytics_finance_month=ANALYTICS_FINANCE_MONTH_PAYLOAD,
        analytics_finance_year=ANALYTICS_FINANCE_YEAR_PAYLOAD,
        user_profile={"currency": "EUR"},
    )
    states = {item["name"]: item["state"] for item in items}
    labels = {item["name"]: item["label"] for item in items}

    assert states["hems_analytics_finance_month_finance_cost"] == "0.44 EUR"
    assert labels["hems_analytics_finance_month_finance_cost"] == "Month Finance cost"
    assert states["hems_analytics_finance_month_finance_profit"] == "23.31 EUR"
    assert states["hems_analytics_finance_year_finance_cost"] == "11.23 EUR"
    assert states["hems_analytics_finance_year_finance_balance"] == "684.87 EUR"
    assert labels["hems_analytics_finance_year_finance_balance"] == "Year Finance balance"
    assert not any(name.endswith("_latest") for name in states)


def test_hems_payloads_to_items_maps_analytics_work_year_payloads():
    items = hems_payloads_to_items(
        analytics_consumption_year=ANALYTICS_CONSUMPTION_YEAR_PAYLOAD,
        analytics_production_year=ANALYTICS_PRODUCTION_YEAR_PAYLOAD,
    )
    states = {item["name"]: item["state"] for item in items}

    assert states["hems_analytics_consumption_year_consumption_workconsumed"] == "4477.421 kWh"
    assert (
        states["hems_analytics_consumption_year_consumption_workacin"]
        == "2680.271 kWh"
    )
    assert states["hems_analytics_production_year_production_workproduced"] == "11338.531 kWh"
    assert states["hems_analytics_production_year_production_workout"] == "8405.903 kWh"
    assert states["hems_analytics_production_year_production_workbuffered"] == "1046.393 kWh"
    assert (
        states["hems_analytics_production_year_production_workacout"]
        == "11338.531 kWh"
    )
    assert not any(name.endswith("_latest") for name in states)


def test_hems_payloads_to_items_maps_analytics_work_month_payloads():
    items = hems_payloads_to_items(
        analytics_consumption_month=ANALYTICS_CONSUMPTION_MONTH_PAYLOAD,
        analytics_production_month=ANALYTICS_PRODUCTION_MONTH_PAYLOAD,
    )
    states = {item["name"]: item["state"] for item in items}

    assert states["hems_analytics_consumption_month_consumption_workconsumed"] == "83.058 kWh"
    assert (
        states["hems_analytics_consumption_month_consumption_workacin"]
        == "46.874 kWh"
    )
    assert states["hems_analytics_production_month_production_workproduced"] == "203.998 kWh"
    assert states["hems_analytics_production_month_production_workout"] == "211.607 kWh"
    assert states["hems_analytics_production_month_production_workbuffered"] == "44.878 kWh"
    assert (
        states["hems_analytics_production_month_production_workacout"]
        == "203.998 kWh"
    )
    assert not any(name.endswith("_latest") for name in states)


def test_hems_payloads_to_items_maps_storage_and_independence_month_payloads():
    items = hems_payloads_to_items(
        analytics_storage_month=ANALYTICS_STORAGE_MONTH_PAYLOAD,
        analytics_independence_month=ANALYTICS_INDEPENDENCE_MONTH_PAYLOAD,
    )
    states = {item["name"]: item["state"] for item in items}
    labels = {item["name"]: item["label"] for item in items}

    assert states["hems_analytics_storage_month_storage_workacin"] == "64.691 kWh"
    assert (
        labels["hems_analytics_storage_month_storage_workacin"]
        == "Month Storage WorkACIn"
    )
    assert (
        states["hems_analytics_storage_month_storage_workreleased"]
        == "57.093 kWh"
    )
    assert (
        states["hems_analytics_independence_month_independence_autarky"]
        == "98 %"
    )
    assert (
        labels["hems_analytics_independence_month_independence_autarky"]
        == "Month Independence Autarky"
    )
    assert not any(name.endswith("_latest") for name in states)


def test_hems_payloads_to_items_maps_storage_and_independence_year_payloads():
    items = hems_payloads_to_items(
        analytics_storage_year=ANALYTICS_STORAGE_YEAR_PAYLOAD,
        analytics_independence_year=ANALYTICS_INDEPENDENCE_YEAR_PAYLOAD,
    )
    states = {item["name"]: item["state"] for item in items}
    labels = {item["name"]: item["label"] for item in items}

    assert states["hems_analytics_storage_year_storage_workacin"] == "1072.447 kWh"
    assert (
        labels["hems_analytics_storage_year_storage_workacin"]
        == "Year Storage WorkACIn"
    )
    assert (
        states["hems_analytics_storage_year_storage_workbuffered"]
        == "1064.067 kWh"
    )
    assert (
        states["hems_analytics_independence_year_independence_autarky"]
        == "68 %"
    )
    assert (
        labels["hems_analytics_independence_year_independence_autarky"]
        == "Year Independence Autarky"
    )
    assert not any(name.endswith("_latest") for name in states)


def test_hems_payloads_to_items_maps_device_consumption_work_today_payloads():
    items = hems_payloads_to_items(
        analytics_consumption_work_today=ANALYTICS_CONSUMPTION_WORK_TODAY_PAYLOAD,
    )
    states = {item["name"]: item["state"] for item in items}

    assert (
        states["hems_analytics_consumption_today_consumption_workconsumed"]
        == "37.51 kWh"
    )
    assert (
        states[
            "hems_analytics_consumption_today_consumption_keba_p30_pv_edition_workacin"
        ]
        == "25.643 kWh"
    )
    assert (
        states[
            "hems_analytics_consumption_today_consumption_mystrom_waschmaschine_workin"
        ]
        == "0.123 kWh"
    )
    assert (
        states[
            "hems_analytics_consumption_today_consumption_mystrom_wasserpumpe_workin"
        ]
        == "0.456 kWh"
    )
    assert f"hems_evstation_{EVSTATION_ID.replace('-', '_')}_today_consumption_workacin" not in states
    assert f"hems_evstation_{EVSTATION_ID.replace('-', '_')}_today_workacin" not in states
    assert "hems_analytics_consumption_today_consumption_workin" not in states


def test_hems_payloads_to_things_adds_new_hems_summary_channels():
    things = hems_payloads_to_things(
        analytics_finance=ANALYTICS_FINANCE_PAYLOAD,
        analytics_production_year=ANALYTICS_PRODUCTION_YEAR_PAYLOAD,
    )
    thing_types = {thing["thingTypeUID"] for thing in things}

    assert "kiwigrid-hems:analytics_finance" in thing_types
    assert "kiwigrid-hems:analytics_production" in thing_types


def test_hems_payloads_to_things_groups_synthetic_periods_under_one_device():
    things = hems_payloads_to_things(
        analytics_consumption=ANALYTICS_CONSUMPTION_PAYLOAD,
        analytics_consumption_month=ANALYTICS_CONSUMPTION_MONTH_PAYLOAD,
        analytics_consumption_year=ANALYTICS_CONSUMPTION_YEAR_PAYLOAD,
        analytics_storage_month=ANALYTICS_STORAGE_MONTH_PAYLOAD,
        analytics_independence_year=ANALYTICS_INDEPENDENCE_YEAR_PAYLOAD,
        analytics_finance_month=ANALYTICS_FINANCE_MONTH_PAYLOAD,
        analytics_finance_year=ANALYTICS_FINANCE_YEAR_PAYLOAD,
    )

    assert {thing["UID"] for thing in things} == {"kiwigrid-hems"}
    linked_items = {
        linked_item
        for thing in things
        for channel in thing["channels"]
        for linked_item in channel["linkedItems"]
    }
    assert "hems_analytics_consumption_today_consumption_powerconsumed" in linked_items
    assert "hems_analytics_consumption_month_consumption_workconsumed" in linked_items
    assert "hems_analytics_consumption_year_consumption_workconsumed" in linked_items
    assert "hems_analytics_storage_month_storage_workacin" in linked_items
    assert "hems_analytics_independence_year_independence_autarky" in linked_items
    assert "hems_analytics_finance_month_finance_cost" in linked_items
    assert "hems_analytics_finance_year_finance_balance" in linked_items
