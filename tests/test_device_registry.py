from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from .module_loader import load_component_module_with_stubs, make_homeassistant_stubs, make_module


DOMAIN = "solarwatt_manager"
PACKAGE_NAME = "solarwatt_manager_device_registry_test"


class ModernDevice(SimpleNamespace):
    @property
    def config_entries(self):
        raise AssertionError("Deprecated config_entries property was accessed")


class ModernRegistry:
    def __init__(self, devices=()):
        self.devices = {device.id: device for device in devices}
        self.removed = []

    def async_get_device(self, **kwargs):
        raise AssertionError("Deprecated device lookup was called")

    def async_get_device_by_identifier(self, identifier, config_entry_id):
        return next(
            (
                device for device in self.devices.values()
                if identifier in device.identifiers
                and device.config_entry_id == config_entry_id
            ),
            None,
        )

    def async_get_or_create(self, *, config_entry_id, **info):
        assert "via_device" not in info
        identifier = next(iter(info["identifiers"]))
        device = self.async_get_device_by_identifier(identifier, config_entry_id)
        if device is None:
            device = ModernDevice(
                id=f"device-{len(self.devices)}", config_entry_id=config_entry_id, **info
            )
            self.devices[device.id] = device
        return device

    def async_remove_device(self, device_id):
        self.removed.append(device_id)
        del self.devices[device_id]

    def async_update_device(self, *, device_id, new_identifiers):
        self.devices[device_id].identifiers = new_identifiers


class LegacyRegistry:
    def __init__(self, device):
        self.device = device

    def async_get_device(self, *, identifiers):
        return self.device if identifiers & self.device.identifiers else None

    def async_update_device(self, *, device_id, remove_config_entry_id):
        assert device_id == self.device.id
        self.device.config_entries.remove(remove_config_entry_id)


@pytest.fixture
def modules():
    stubs = {
        **make_homeassistant_stubs(),
        f"{PACKAGE_NAME}.hems_api": make_module(
            f"{PACKAGE_NAME}.hems_api", is_hems_thing=lambda thing: False
        ),
    }
    loaded = {}
    for name in (
        "registry", "const", "entity_helpers", "registry_cleanup",
        "registry_migrations", "diagnostics",
    ):
        loaded[name] = load_component_module_with_stubs(
            name, package_name=PACKAGE_NAME, stubs=stubs
        )
        stubs[f"{PACKAGE_NAME}.{name}"] = loaded[name]
    return SimpleNamespace(**loaded)


def _device(device_id, entry_id, uid="parent"):
    return ModernDevice(
        id=device_id,
        config_entry_id=entry_id,
        identifiers={(DOMAIN, f"installation:{uid}")},
        name="API name",
        name_by_user=f"User name for {entry_id}",
    )


def _things():
    return {
        "parent": {
            "UID": "parent", "bridgeUID": "bridge",
            "thingTypeUID": "inverter", "channels": [{}],
        },
        "child": {
            "UID": "child", "bridgeUID": "bridge",
            "thingTypeUID": "battery", "channels": [{}],
        },
    }


def _entry():
    return SimpleNamespace(
        entry_id="entry", data={"installation_id": "installation"}, options={}
    )


def test_lookup_and_custom_device_name_are_scoped_to_config_entry(modules):
    other = _device("other-device", "other-entry")
    own = _device("own-device", "entry")
    hass = SimpleNamespace(devices=ModernRegistry([other, own]))
    identifier = (DOMAIN, "installation:parent")

    assert modules.registry.get_device_by_identifier(hass.devices, identifier, "entry") is own
    assert modules.const.get_registry_device_name(hass, identifier, "entry") == own.name_by_user
    assert modules.const.get_registry_device_name(hass, identifier, "missing") is None


@pytest.mark.parametrize("parent_state", ["registered", "missing", "deselected"])
def test_parent_links_use_only_an_owned_registered_selected_device(modules, parent_state):
    devices = [_device("other-parent", "other-entry")]
    if parent_state != "missing":
        devices.append(_device("own-parent", "entry"))
    hass = SimpleNamespace(devices=ModernRegistry(devices))
    things = _things()
    selected = {"child"} if parent_state == "deselected" else None

    info = modules.const.build_thing_device_info(
        hass, "installation", things["child"], things, selected,
        config_entry_id="entry",
    )

    assert "via_device" not in info
    assert info["via_device_id"] == ("own-parent" if parent_state == "registered" else None)
    assert info["identifiers"] == {(DOMAIN, "installation:child")}


def test_parent_is_registered_before_child_metadata_is_built(modules):
    hass = SimpleNamespace(devices=ModernRegistry())
    things = _things()

    modules.entity_helpers.ensure_parent_devices_registered(hass, _entry(), things)
    info = modules.const.build_thing_device_info(
        hass, "installation", things["child"], things, config_entry_id="entry"
    )

    parent = hass.devices.async_get_device_by_identifier((DOMAIN, "installation:parent"), "entry")
    assert parent is not None
    assert info["via_device_id"] == parent.id
    assert "via_device" not in info


def test_legacy_parent_link_and_shared_device_detachment_are_preserved(modules):
    parent = SimpleNamespace(
        id="legacy-parent", identifiers={(DOMAIN, "installation:parent")},
        config_entries={"entry", "other-entry"},
    )
    registry = LegacyRegistry(parent)
    hass = SimpleNamespace(devices=registry)
    things = _things()

    info = modules.const.build_thing_device_info(
        hass, "installation", things["child"], things, config_entry_id="entry"
    )
    assert info["via_device"] == (DOMAIN, "installation:parent")
    assert "via_device_id" not in info

    modules.registry.remove_device_config_entry(registry, parent, "entry")
    assert parent.config_entries == {"other-entry"}


@pytest.mark.parametrize("operation", ["selection", "entityless", "orphaned"])
@pytest.mark.parametrize("keep_device", [False, True])
def test_device_cleanup_preserves_other_config_entries(modules, operation, keep_device):
    own = _device("own-device", "entry")
    other = _device("other-device", "other-entry")
    registry = ModernRegistry([other, own])
    entity_entries = (
        [SimpleNamespace(platform=DOMAIN, device_id=own.id, unique_id="entry_power")]
        if keep_device else []
    )
    hass = SimpleNamespace(devices=registry, entities=SimpleNamespace(entries=entity_entries))
    entry = _entry()
    if operation == "selection":
        modules.entity_helpers._sync_thing_device_assignments(
            hass, entry, {"parent": {}}, {"parent"} if keep_device else set()
        )
    elif operation == "entityless":
        modules.entity_helpers.detach_entityless_thing_devices(hass, entry, {"parent": {}})
    else:
        modules.registry_cleanup.cleanup_empty_channel_thing_diagnostics(
            hass, entry, {"parent": {"channels": []}}
        )

    assert registry.removed == ([] if keep_device else [own.id])
    assert registry.devices[other.id] is other


def test_removing_a_device_owned_by_another_entry_is_ignored(modules):
    other = _device("other-device", "other-entry")
    registry = ModernRegistry([other])

    modules.registry.remove_device_config_entry(registry, other, "entry")

    assert registry.removed == []


def test_empty_channel_cleanup_removes_diagnostics_before_checking_devices(modules):
    empty = _device("empty-device", "entry", "empty")
    active = _device("active-device", "entry", "active")
    registry = ModernRegistry([empty, active])
    diagnostic = SimpleNamespace(
        entity_id="sensor.empty_diagnostics", platform=DOMAIN,
        unique_id="entry_thing_empty", device_id=empty.id,
    )
    entities = SimpleNamespace(entries=[diagnostic])

    def remove_entity(entity_id):
        entities.entries = [item for item in entities.entries if item.entity_id != entity_id]

    entities.async_remove = remove_entity
    hass = SimpleNamespace(devices=registry, entities=entities)

    modules.registry_cleanup.cleanup_empty_channel_thing_diagnostics(
        hass, _entry(), {"empty": {"channels": []}, "active": {"channels": [{}]}}
    )

    assert entities.entries == []
    assert registry.removed == [empty.id]
    assert registry.devices[active.id] is active


@pytest.mark.parametrize(
    ("properties", "fallback", "expected"),
    [
        ({"identifier": " 12345678-1234-1234-1234-123456789abc "}, "thing", "12345678-1234-1234-1234-123456789abc"),
        ({"identifier": ""}, "thing", "thing"),
        ({}, " thing ", "thing"),
        (None, "thing", "thing"),
        ([], "thing", "thing"),
        ({}, "", ""),
    ],
)
def test_shared_hems_device_id_preserves_control_target(modules, properties, fallback, expected):
    assert modules.entity_helpers.get_hems_device_id({"properties": properties}, fallback) == expected


@pytest.mark.parametrize("target_exists", [False, True])
def test_identifier_migration_only_changes_owned_devices(modules, target_exists):
    old_identifier = (DOMAIN, "installation:parent")
    new_identifier = (DOMAIN, "stable:parent")
    own = _device("own-device", "entry")
    other = _device("other-device", "other-entry")
    other_target = _device("other-target", "other-entry")
    other_target.identifiers = {new_identifier}
    devices = [other, other_target, own]
    target = _device("own-target", "entry")
    target.identifiers = {new_identifier}
    if target_exists:
        devices.append(target)
    registry = ModernRegistry(devices)
    entity = SimpleNamespace(
        entity_id="sensor.power", unique_id="entry_power", device_id=own.id
    )

    def update_entity(entity_id, *, device_id):
        assert entity_id == entity.entity_id
        entity.device_id = device_id

    migrated = modules.registry_migrations._migrate_device_identifier(
        registry, SimpleNamespace(async_update_entity=update_entity), _entry(),
        [entity], old_identifier, new_identifier,
    )

    assert migrated == 1
    assert entity.unique_id == "entry_power"
    assert entity.device_id == (target.id if target_exists else own.id)
    assert registry.removed == ([own.id] if target_exists else [])
    assert other.identifiers == {old_identifier}
    assert registry.devices[other_target.id] is other_target
    if not target_exists:
        assert own.identifiers == {new_identifier}


def test_diagnostics_uses_the_device_owned_by_the_entry(modules):
    own = _device("own-device", "entry")
    other = _device("other-device", "other-entry")
    for device in (other, own):
        device.identifiers = {(DOMAIN, "installation")}
        device.manufacturer = "SOLARWATT"
        device.model = "Manager"
        device.sw_version = None
        device.hw_version = None
    own.name = "Own Manager"
    other.name = "Other Manager"
    own.model = "Own model"
    entry = _entry()
    entry.title = "SOLARWATT"
    entry.domain = DOMAIN
    entry.runtime_data = SimpleNamespace(data={}, things={})
    hass = SimpleNamespace(
        devices=ModernRegistry([other, own]), entities=SimpleNamespace(entries=[])
    )

    result = asyncio.run(modules.diagnostics.async_get_config_entry_diagnostics(hass, entry))

    assert result["device"]["name"] == "REDACTED"
    assert result["device"]["model"] == "Own model"
