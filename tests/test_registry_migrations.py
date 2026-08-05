from __future__ import annotations

from types import SimpleNamespace

from .module_loader import load_component_module_with_stubs, make_module


PACKAGE_NAME = "solarwatt_manager_registry_migrations_test"


class FakeDeviceRegistry:
    def __init__(self, devices):
        self.devices = {device.id: device for device in devices}

    def async_get_device(self, *, identifiers):
        return next(
            (
                device
                for device in self.devices.values()
                if set(identifiers) & device.identifiers
            ),
            None,
        )

    def async_update_device(self, *, device_id, **changes):
        device = self.devices[device_id]
        if "new_identifiers" in changes:
            device.identifiers = set(changes["new_identifiers"])
        if config_entry_id := changes.get("add_config_entry_id"):
            device.config_entries.add(config_entry_id)
        if config_entry_id := changes.get("remove_config_entry_id"):
            device.config_entries.discard(config_entry_id)


class FakeEntityRegistry:
    def __init__(self, entries):
        self.entries = entries

    def async_update_entity(self, entity_id, *, device_id):
        next(
            entry for entry in self.entries if entry.entity_id == entity_id
        ).device_id = device_id

    def async_remove(self, entity_id):
        self.entries[:] = [
            entry for entry in self.entries if entry.entity_id != entity_id
        ]


class FakeConfigEntries:
    def __init__(self, entry):
        self.entry = entry

    def async_entries(self, domain):
        return [self.entry]

    def async_update_entry(self, entry, **changes):
        if "data" in changes:
            entry.data = changes["data"]
        if "unique_id" in changes:
            entry.unique_id = changes["unique_id"]


def _load_registry_migrations(device_registry, entity_registry):
    dr = make_module(
        "homeassistant.helpers.device_registry",
        DeviceRegistry=object,
        async_get=lambda hass: device_registry,
    )
    er = make_module(
        "homeassistant.helpers.entity_registry",
        EntityRegistry=object,
        RegistryEntry=object,
        async_get=lambda hass: entity_registry,
        async_entries_for_config_entry=lambda registry, entry_id: registry.entries,
    )
    return load_component_module_with_stubs(
        "registry_migrations",
        package_name=PACKAGE_NAME,
        stubs={
            "homeassistant": make_module("homeassistant"),
            "homeassistant.core": make_module(
                "homeassistant.core",
                HomeAssistant=object,
            ),
            "homeassistant.helpers": make_module(
                "homeassistant.helpers",
                device_registry=dr,
                entity_registry=er,
            ),
            "homeassistant.helpers.device_registry": dr,
            "homeassistant.helpers.entity_registry": er,
            f"{PACKAGE_NAME}.const": make_module(
                f"{PACKAGE_NAME}.const",
                CONF_HOST="host",
                CONF_INSTALLATION_ID="installation_id",
                DOMAIN="solarwatt_manager",
                SOLARWATTConfigEntry=object,
                build_thing_device_identifier=lambda anchor, uid: (
                    "solarwatt_manager",
                    f"{anchor}:{uid}",
                ),
                derive_installation_id=lambda data, options, things: (
                    "local:location-uid"
                ),
                get_device_registry_anchor=lambda entry: (
                    entry.data.get("installation_id")
                    or entry.data.get("host")
                    or entry.entry_id
                ),
            ),
        },
    )


def test_host_based_device_identifiers_are_migrated_in_place():
    root_device = SimpleNamespace(
        id="root-device",
        identifiers={("solarwatt_manager", "192.0.2.10")},
        config_entries={"entry-id"},
    )
    thing_device = SimpleNamespace(
        id="thing-device",
        identifiers={("solarwatt_manager", "192.0.2.10:thing-1")},
        config_entries={"entry-id"},
    )
    registry_entry = SimpleNamespace(
        entity_id="sensor.manager_power",
        unique_id="entry-id_power",
        device_id="thing-device",
        platform="solarwatt_manager",
    )
    device_registry = FakeDeviceRegistry([root_device, thing_device])
    entity_registry = FakeEntityRegistry([registry_entry])
    migrations = _load_registry_migrations(device_registry, entity_registry)
    entry = SimpleNamespace(
        entry_id="entry-id",
        unique_id="192.0.2.10",
        data={"host": "192.0.2.10"},
        options={},
    )
    hass = SimpleNamespace(config_entries=FakeConfigEntries(entry))

    migrations.migrate_device_registry_identifiers(
        hass,
        entry,
        {"thing-1": {"UID": "thing-1"}},
    )

    assert root_device.identifiers == {("solarwatt_manager", "local:location-uid")}
    assert thing_device.identifiers == {
        ("solarwatt_manager", "local:location-uid:thing-1")
    }
    assert registry_entry.device_id == "thing-device"
    assert registry_entry.unique_id == "entry-id_power"
    assert entry.data["installation_id"] == "local:location-uid"
    assert entry.unique_id == "local:location-uid"
