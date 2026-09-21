from __future__ import annotations

from types import SimpleNamespace

from .module_loader import load_component_module, load_component_module_with_stubs, make_module


PACKAGE_NAME = "solarwatt_manager_entity_helpers_cloud_test"


class FakeDeviceRegistry:
    def __init__(self):
        self.lookups = []
        self.updates = []
        self.device = SimpleNamespace(id="device-id", config_entries={"cloud-entry"})

    def async_get_device(self, *, identifiers):
        self.lookups.append(identifiers)
        return self.device

    def async_update_device(self, **kwargs):
        self.updates.append(kwargs)


device_registry = FakeDeviceRegistry()
dr = make_module(
    "homeassistant.helpers.device_registry",
    async_get=lambda hass: device_registry,
)
er = make_module(
    "homeassistant.helpers.entity_registry",
    EntityRegistry=object,
    RegistryEntry=object,
    RegistryEntryDisabler=SimpleNamespace(INTEGRATION="integration", USER="user"),
)

entity_helpers = load_component_module_with_stubs(
    "entity_helpers",
    package_name=PACKAGE_NAME,
    stubs={
        "homeassistant": make_module("homeassistant"),
        "homeassistant.core": make_module(
            "homeassistant.core",
            HomeAssistant=object,
            callback=lambda func: func,
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
            DOMAIN="solarwatt_manager",
            SOLARWATTConfigEntry=object,
            build_thing_device_identifier=lambda anchor, uid: (
                "solarwatt_manager",
                f"{anchor}:{uid}",
            ),
            build_thing_device_info=lambda *args: {},
            get_device_registry_anchor=lambda entry: (
                entry.data.get("host") or entry.entry_id
            ),
            get_preferred_parent_thing_uid=lambda *args: None,
            get_selected_thing_uids=lambda options: None,
        ),
        f"{PACKAGE_NAME}.naming": make_module(
            f"{PACKAGE_NAME}.naming",
            clean_item_key=lambda value: value,
        ),
    },
)


def test_cloud_only_device_selection_uses_entry_id_as_registry_anchor():
    device_registry.lookups.clear()
    device_registry.updates.clear()
    entry = SimpleNamespace(entry_id="cloud-entry", data={})

    entity_helpers._sync_thing_device_assignments(
        object(),
        entry,
        {"thing-uid": {}},
        set(),
    )

    assert device_registry.lookups == [
        {("solarwatt_manager", "cloud-entry:thing-uid")}
    ]
    assert device_registry.updates == [
        {
            "device_id": "device-id",
            "remove_config_entry_id": "cloud-entry",
        }
    ]


def test_battery_backup_items_are_discovered_as_sensors_for_the_selected_battery():
    hems_client = load_component_module("hems_client")
    battery_id = "704de3e0-1111-2222-3333-444444444444"
    raw_items = hems_client.battery_endpoint_to_items([{
        "id": battery_id,
        "backup_active": False,
        "backup_available": True,
        "backup_state_of_charge": 0.15,
        "mode": "DISCHARGING",
        "state_of_charge": 0.92,
    }])
    items = {
        item["name"]: SimpleNamespace(oh_type=item["type"])
        for item in raw_items
    }
    owners = dict.fromkeys(items, battery_id)
    prefix = f"hems_battery_{battery_id.replace('-', '_')}_"
    expected = {
        f"{prefix}{suffix}" for suffix in (
            "backup_active", "backup_available", "backup_state_of_charge",
            "mode", "state_of_charge",
        )
    }

    assert set(entity_helpers.iter_item_sensor_names(items, owners, {battery_id})) == expected
    assert list(entity_helpers.iter_item_sensor_names(items, owners, set())) == []
