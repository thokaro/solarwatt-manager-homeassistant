from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from .module_loader import load_component_module_with_stubs, make_homeassistant_stubs, make_module


class FakeCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def async_write_ha_state(self):
        pass


@pytest.fixture
def platforms():
    package = "solarwatt_manager_control_platform_test"
    stubs = {
        **make_homeassistant_stubs(),
        "homeassistant.exceptions": make_module(
            "homeassistant.exceptions", HomeAssistantError=RuntimeError
        ),
        "homeassistant.helpers.entity_platform": make_module(
            "homeassistant.helpers.entity_platform", AddEntitiesCallback=object
        ),
        "homeassistant.helpers.update_coordinator": make_module(
            "homeassistant.helpers.update_coordinator", CoordinatorEntity=FakeCoordinatorEntity
        ),
        "homeassistant.components.select": make_module(
            "homeassistant.components.select", SelectEntity=type("SelectEntity", (), {})
        ),
        "homeassistant.components.switch": make_module(
            "homeassistant.components.switch", SwitchEntity=type("SwitchEntity", (), {})
        ),
    }
    loaded = {}
    for name in ("const", "entity_helpers", "select", "switch"):
        loaded[name] = load_component_module_with_stubs(name, package_name=package, stubs=stubs)
        stubs[f"{package}.{name}"] = loaded[name]
    return SimpleNamespace(**loaded)


def _thing(uid="thing", **properties):
    return {
        "UID": uid,
        "label": "API device name",
        "properties": {
            "optimizationSupportsSwitching": "true",
            "optimizationSupportedModes": "NOT_OPTIMIZED,PV_EXCESS",
            "identifier": "12345678-1234-1234-1234-123456789abc",
            **properties,
        },
    }


def _setup(platform, things, options=None, entry_id="entry"):
    callbacks = []
    unload_callbacks = []

    def register(callback):
        callbacks.append(callback)
        return lambda: callbacks.remove(callback)

    entry = SimpleNamespace(
        entry_id=entry_id, options=options or {}, data={"installation_id": "installation"},
        async_on_unload=unload_callbacks.append,
    )
    coordinator = SimpleNamespace(
        entry=entry, hass=SimpleNamespace(devices=None), things=things,
        client=SimpleNamespace(host="manager.local"),
        register_discovery_callback=register,
        async_set_hems_device_optimization_mode=AsyncMock(),
        async_set_hems_device_optimization_state=AsyncMock(),
    )
    entry.runtime_data = coordinator
    batches = []
    asyncio.run(platform.async_setup_entry(coordinator.hass, entry, batches.append))
    return SimpleNamespace(
        entry=entry, coordinator=coordinator, batches=batches,
        callbacks=callbacks, unload_callbacks=unload_callbacks,
    )


@pytest.mark.parametrize("platform", ["select", "switch"])
@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        ({}, {"select", "switch"}),
        ({"optimizationSupportedModes": "NOT_OPTIMIZED"}, {"switch"}),
        ({"optimizationSupportedModes": "NOT_OPTIMIZED,NOT_OPTIMIZED"}, {"switch"}),
        ({"optimizationSupportedModes": ""}, {"switch"}),
        ({"optimizationSupportsSwitching": "false"}, set()),
        ({"optimizationSupportsSwitching": " TRUE "}, {"select", "switch"}),
    ],
)
def test_discovery_keeps_platform_capability_rules(platforms, platform, properties, expected):
    rig = _setup(getattr(platforms, platform), {"thing": _thing(**properties)})

    assert len(rig.batches) == (1 if platform in expected else 0)
    if rig.batches:
        entity = rig.batches[0][0]
        suffix = "evstation_optimization_mode" if platform == "select" else "optimization_switch"
        assert entity._attr_unique_id == f"entry_thing_thing_{suffix}"
        assert entity._attr_device_info["identifiers"] == {("solarwatt_manager", "installation:thing")}
        assert entity._attr_device_info["name"] == "API device name"


@pytest.mark.parametrize("platform", ["select", "switch"])
def test_discovery_selection_updates_and_unload(platforms, platform):
    rig = _setup(
        getattr(platforms, platform), {"first": _thing("first"), "second": _thing("second")},
        {"enabled_things": ["first"]},
    )
    assert [entity._thing_uid for entity in rig.batches[0]] == ["first"]
    assert len(rig.callbacks) == len(rig.unload_callbacks) == 1
    discover = rig.callbacks[0]

    discover()
    discover({"enabled_things": []})
    assert len(rig.batches) == 1
    discover({"enabled_things": ["second"]})
    assert [entity._thing_uid for entity in rig.batches[1]] == ["second"]
    rig.coordinator.things["third"] = _thing("third")
    discover({})
    assert [entity._thing_uid for entity in rig.batches[2]] == ["third"]
    rig.entry.options = {"enabled_things": ["first", "second", "third"]}
    discover()
    assert len(rig.batches) == 3

    rig.unload_callbacks[0]()
    assert rig.callbacks == []


@pytest.mark.parametrize("platform", ["select", "switch"])
def test_skipped_devices_can_be_discovered_when_metadata_arrives(platforms, platform):
    things = {
        "unsupported": _thing("unsupported", optimizationSupportsSwitching="false"),
        "no-id": _thing("no-id", identifier=" "),
        "no-properties": {"UID": "no-properties", "properties": []},
    }
    rig = _setup(getattr(platforms, platform), things)
    assert rig.batches == []

    things["unsupported"] = _thing("unsupported")
    things["no-id"] = _thing("no-id")
    things["no-properties"] = _thing("no-properties")
    rig.callbacks[0]()
    assert [entity._thing_uid for entity in rig.batches[0]] == list(things)
    rig.callbacks[0]()
    assert len(rig.batches) == 1


@pytest.mark.parametrize("platform", ["select", "switch"])
def test_initially_empty_discovery_uses_latest_coordinator_data(platforms, platform):
    rig = _setup(getattr(platforms, platform), None)
    assert rig.batches == []
    rig.coordinator.things = {"new": _thing("new")}
    rig.callbacks[0]()
    assert [entity._thing_uid for entity in rig.batches[0]] == ["new"]


@pytest.mark.parametrize("platform", ["select", "switch"])
@pytest.mark.parametrize("identifier", ["remote-control-id", None])
def test_discovered_entities_send_commands_to_the_correct_device(platforms, platform, identifier):
    uid = "12345678-1234-1234-1234-123456789abc"
    rig = _setup(getattr(platforms, platform), {uid: _thing(uid, identifier=identifier)})
    entity = rig.batches[0][0]

    if platform == "select":
        asyncio.run(entity.async_select_option("pv_excess"))
        rig.coordinator.async_set_hems_device_optimization_mode.assert_awaited_once_with(
            identifier or uid, "PV_EXCESS"
        )
    else:
        asyncio.run(entity.async_turn_on())
        rig.coordinator.async_set_hems_device_optimization_state.assert_awaited_once_with(
            identifier or uid, "ON"
        )


def test_select_and_switch_discovery_are_independent_for_the_same_entry(platforms):
    rig = _setup(platforms.select, {"thing": _thing()})
    switch_batches = []
    asyncio.run(platforms.switch.async_setup_entry(rig.coordinator.hass, rig.entry, switch_batches.append))
    assert len(rig.batches[0]) == len(switch_batches[0]) == 1
    assert rig.batches[0][0]._attr_unique_id != switch_batches[0][0]._attr_unique_id
    for discover in rig.callbacks:
        discover()
    assert len(rig.batches) == len(switch_batches) == 1
