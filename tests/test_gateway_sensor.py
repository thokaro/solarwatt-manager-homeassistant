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
            SensorDeviceClass=SimpleNamespace(ENERGY="energy", POWER="power"),
            SensorStateClass=SimpleNamespace(
                MEASUREMENT="measurement", TOTAL="total", TOTAL_INCREASING="total_increasing"
            ),
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


@pytest.mark.parametrize("selected", [True, False])
def test_selfsupply_sensor_discovery_and_translation(modules, selected):
    uid = modules.hems_api.KIWIGRID_FLOW_THING_UID
    descriptions = modules.sensor.SELFSUPPLY_DESCRIPTIONS
    entry = SimpleNamespace(entry_id="entry", title="Manager", data={"installation_id": "installation"})
    coordinator = SimpleNamespace(
        entry=entry, hass=SimpleNamespace(devices=None),
        client=SimpleNamespace(host=""),
        things={uid: modules.hems_api.kiwigrid_flow_thing()},
        data={name: SimpleNamespace(
            raw={}, parsed=SimpleNamespace(value=75.0),
            oh_type="Number:Dimensionless", label=None,
        ) for name in descriptions},
        item_to_thing_uid=dict.fromkeys(descriptions, uid),
        item_to_channel_metadata={}, stats_total_store=None,
    )
    added_items, added_totals, added_things = set(), set(), set()

    def discover():
        return modules.sensor._collect_new_entities(
            coordinator, entry, {}, {uid} if selected else set(), 0.01, 3,
            added_items, added_totals, added_things,
        )

    sensors = [entity for entity in discover() if isinstance(
        entity, modules.sensor.SOLARWATTItemSensor
    )]
    assert len(sensors) == (7 if selected else 0)
    assert discover() == []
    for sensor in sensors:
        assert sensor._attr_has_entity_name is True
        assert sensor.entity_description.translation_key in {
            "self_sufficiency", "self_consumption",
            "self_sufficiency_composition_battery", "self_sufficiency_composition_pv",
            "consumption_composition_battery", "consumption_composition_grid", "consumption_composition_pv",
        }
        assert sensor._attr_native_unit_of_measurement == "%"
        assert sensor._attr_state_class == "measurement"
        assert sensor._attr_device_class is None
        assert sensor.native_value == 75.0
        assert sensor._sync_display_name() is False
        assert sensor._attr_unique_id == modules.entity_helpers.build_item_sensor_unique_id(
            "entry", sensor.entity_description.key,
        )
        assert sensor._attr_device_info["identifiers"] == {
            ("solarwatt_manager", f"installation:{uid}")
        }


@pytest.mark.parametrize("language,expected", [("de", "Autarkie"), ("en", "Self-sufficiency")])
def test_explicit_sensor_language_overrides_ui_locale_without_changing_ids(modules, language, expected):
    import json
    from pathlib import Path

    translations = json.loads((Path(__file__).parents[1] / 'custom_components' / 'solarwatt_manager' / 'translations' / f'{language}.json').read_text())['entity']['sensor']
    uid = modules.hems_api.KIWIGRID_FLOW_THING_UID
    name = 'hems_flow_self_sufficiency'
    entry = SimpleNamespace(entry_id='entry', title='Manager', data={'installation_id': 'installation'})
    coordinator = SimpleNamespace(
        entry=entry, hass=SimpleNamespace(devices=None), client=SimpleNamespace(host=''),
        things={uid: modules.hems_api.kiwigrid_flow_thing()},
        data={name: SimpleNamespace(raw={}, parsed=SimpleNamespace(value=100), oh_type='Number:Dimensionless', label=None)},
        item_to_thing_uid={name: uid}, item_to_channel_metadata={},
        sensor_name_translations={k: v['name'] for k, v in translations.items()},
    )
    sensor = modules.sensor.SOLARWATTItemSensor(coordinator, 'entry', name)
    assert sensor._attr_name == expected
    assert sensor._attr_unique_id == modules.entity_helpers.build_item_sensor_unique_id('entry', name)
    assert sensor.native_value == 100
    assert sensor._sync_display_name() is False


@pytest.mark.parametrize('options,ha_language,language', [
    ({}, 'de', 'de'), ({}, 'en', 'en'), ({}, 'fr', 'en'),
    ({'sensor_name_language': 'auto'}, 'de-DE', 'de'),
    ({'sensor_name_language': 'auto'}, 'de_CH', 'de'),
    ({'sensor_name_language': 'auto'}, 'nl', 'en'),
    ({'sensor_name_language': 'en'}, 'de', 'en'),
    ({'sensor_name_language': 'de'}, 'en', 'de'),
])
def test_sensor_setup_loads_configured_language_once(modules, monkeypatch, options, ha_language, language):
    import asyncio
    import sys
    from unittest.mock import AsyncMock

    loader = AsyncMock(return_value={
        'component.solarwatt_manager.entity.sensor.self_sufficiency.name': 'Translated',
        'component.solarwatt_manager.entity.button.override_reset.name': 'Button',
    })
    monkeypatch.setitem(sys.modules, 'homeassistant.helpers.translation', make_module(
        'homeassistant.helpers.translation', async_get_translations=loader,
    ))
    callbacks = []
    coordinator = SimpleNamespace(things={}, data={}, item_to_thing_uid={}, register_discovery_callback=lambda cb: callbacks.append(cb))
    entry = SimpleNamespace(options=options, runtime_data=coordinator, async_on_unload=lambda cb: None)
    hass = SimpleNamespace(config=SimpleNamespace(language=ha_language))
    asyncio.run(modules.sensor.async_setup_entry(hass, entry, lambda entities: None))
    loader.assert_awaited_once_with(hass, language, 'entity', {'solarwatt_manager'})
    assert coordinator.sensor_name_translations == {'self_sufficiency': 'Translated'}
