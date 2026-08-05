from __future__ import annotations

from types import SimpleNamespace

from .module_loader import load_component_module_with_stubs, make_module


PACKAGE_NAME = "solarwatt_manager_identifiers_test"


class FakeConfigEntry:
    @classmethod
    def __class_getitem__(cls, item):
        return cls


class FakeDeviceInfo(dict):
    pass


dr = make_module(
    "homeassistant.helpers.device_registry",
    DeviceEntry=object,
    DeviceInfo=FakeDeviceInfo,
    async_get=lambda hass: None,
)

const = load_component_module_with_stubs(
    "const",
    package_name=PACKAGE_NAME,
    stubs={
        "homeassistant": make_module("homeassistant"),
        "homeassistant.config_entries": make_module(
            "homeassistant.config_entries",
            ConfigEntry=FakeConfigEntry,
        ),
        "homeassistant.core": make_module(
            "homeassistant.core",
            HomeAssistant=object,
        ),
        "homeassistant.helpers": make_module(
            "homeassistant.helpers",
            device_registry=dr,
        ),
        "homeassistant.helpers.device_registry": dr,
    },
)


def test_local_installation_id_uses_location_uid_instead_of_host():
    things = {
        "kiwigrid-location:standard:manager-uid": {
            "UID": "kiwigrid-location:standard:manager-uid",
            "thingTypeUID": "kiwigrid-location:standard",
        }
    }

    first = const.derive_installation_id({"host": "192.0.2.1"}, {}, things)
    second = const.derive_installation_id({"host": "manager.local"}, {}, things)

    assert first == "local:kiwigrid-location:standard:manager-uid"
    assert second == first


def test_existing_installation_id_is_not_replaced():
    entry_data = {
        "host": "manager.local",
        "installation_id": "local:original-location",
    }
    things = {
        "replacement": {
            "UID": "replacement",
            "thingTypeUID": "kiwigrid-location:standard",
        }
    }

    assert (
        const.derive_installation_id(entry_data, {}, things)
        == "local:original-location"
    )


def test_manager_fallback_survives_host_change_until_location_is_available():
    fallback_id = const.derive_installation_id({"host": "192.0.2.1"}, {})

    assert fallback_id.startswith("manager:")
    assert (
        const.derive_installation_id(
            {
                "host": "manager.local",
                "installation_id": fallback_id,
            },
            {},
        )
        == fallback_id
    )


def test_cloud_installation_id_is_stable_and_hides_username():
    options = {
        "kiwigrid_hems_enabled": True,
        "kiwigrid_hems_username": "Owner@Example.com",
    }
    case_variant = {
        **options,
        "kiwigrid_hems_username": "owner@example.com",
    }

    installation_id = const.derive_installation_id({"host": None}, options)

    assert installation_id == const.derive_installation_id({"host": None}, case_variant)
    assert installation_id.startswith("hems:")
    assert "owner@example.com" not in installation_id


def test_device_registry_anchor_and_configuration_host_are_independent():
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={
            "host": "192.0.2.10",
            "installation_id": "local:manager-uid",
        },
    )

    assert const.get_device_registry_anchor(entry) == "local:manager-uid"
    assert const.build_device_info(
        "local:manager-uid",
        "Manager",
        "192.0.2.10",
    ) == {
        "identifiers": {("solarwatt_manager", "local:manager-uid")},
        "name": "Manager",
        "manufacturer": "SOLARWATT",
        "model": "Manager flex / rail",
        "configuration_url": "http://192.0.2.10",
    }


def test_thing_display_name_normalizes_acronyms_only():
    thing = {"label": "my Pv battery Soc and Ev charger"}

    assert const.get_thing_display_name(thing) == (
        "my PV battery SoC and EV charger"
    )
