from __future__ import annotations

from types import SimpleNamespace

import pytest

from .module_loader import load_component_module_with_stubs, make_homeassistant_stubs, make_module


@pytest.fixture
def modules():
    package = "solarwatt_gateway_sensor_test"

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    stubs = {
        **make_homeassistant_stubs(),
        "homeassistant.components.sensor": make_module(
            "homeassistant.components.sensor",
            SensorEntity=type("SensorEntity", (), {}),
            SensorEntityDescription=SimpleNamespace,
            SensorDeviceClass=SimpleNamespace(ENERGY="energy"),
            SensorStateClass=SimpleNamespace(TOTAL_INCREASING="total_increasing"),
        ),
        "homeassistant.helpers.entity": make_module(
            "homeassistant.helpers.entity", EntityCategory=SimpleNamespace(DIAGNOSTIC="diagnostic")
        ),
        "homeassistant.helpers.entity_platform": make_module(
            "homeassistant.helpers.entity_platform", AddEntitiesCallback=object
        ),
        "homeassistant.helpers.update_coordinator": make_module(
            "homeassistant.helpers.update_coordinator", CoordinatorEntity=CoordinatorEntity
        ),
        f"{package}.sensor_meta": make_module(
            f"{package}.sensor_meta", guess_ha_meta=lambda *args: {}
        ),
        f"{package}.stats_total": make_module(f"{package}.stats_total", StatsTotalStore=object),
    }
    loaded = {}
    for name in ("hems_api", "const", "entity_helpers", "sensor"):
        loaded[name] = load_component_module_with_stubs(name, package_name=package, stubs=stubs)
        stubs[f"{package}.{name}"] = loaded[name]
    return SimpleNamespace(**loaded)


@pytest.mark.parametrize("selection", [None, set(), {"flow"}])
@pytest.mark.parametrize("local", [False, True])
def test_version_sensor_discovery_respects_flow_selection(modules, selection, local):
    uid = modules.hems_api.ENERGY_OVERVIEW_THING_UID
    selected = {uid} if selection == {"flow"} else selection
    entry = SimpleNamespace(entry_id="entry", data={"installation_id": "installation"})
    coordinator = SimpleNamespace(
        entry=entry, hass=SimpleNamespace(devices=None),
        client=SimpleNamespace(host="manager.local" if local else ""),
        things={uid: modules.hems_api._energy_overview_thing()} if local else {},
        gateway_info={}, data={}, item_to_thing_uid={},
    )
    added_items, added_totals, added_things = set(), set(), set()

    def discover():
        return modules.sensor._collect_new_entities(
            coordinator, entry, {}, selected, 0.01, 3,
            added_items, added_totals, added_things,
        )

    sensors = [entity for entity in discover() if isinstance(
        entity, modules.sensor.SOLARWATTGatewayVersionSensor
    )]
    expected = local and selected != set()
    assert len(sensors) == int(expected)
    assert discover() == []
    if not expected:
        return
    sensor = sensors[0]
    assert sensor._attr_device_info["identifiers"] == {("solarwatt_manager", f"installation:{uid}")}
    assert sensor.entity_description.entity_category == "diagnostic"
    assert sensor.entity_description.translation_key == "kiwi_os_version"
    assert sensor.native_value is None
    coordinator.gateway_info = {"kiwiOsEdgeVersion": "10.26.36.0"}
    assert sensor.native_value == "10.26.36.0"
    coordinator.gateway_info = {"kiwiOsEdgeVersion": "10.27.0.0"}
    assert sensor.native_value == "10.27.0.0"
    expected_ids = modules.entity_helpers._selected_entity_unique_ids(
        entry, {}, {}, {uid}, coordinator.things
    )
    assert sensor._attr_unique_id in expected_ids
    assert sensor._attr_unique_id not in modules.entity_helpers._selected_entity_unique_ids(
        entry, {}, {}, set(), coordinator.things
    )
