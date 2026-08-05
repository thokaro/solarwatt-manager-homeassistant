from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any

import pytest

from .module_loader import load_component_module_with_stubs, make_module


def _load_coordinator_module():
    package_name = "solarwatt_manager_coordinator_test"

    class ConfigEntryAuthFailed(Exception):
        pass

    class SolarwattError(Exception):
        pass

    class SolarwattAuthError(SolarwattError):
        pass

    class DataUpdateCoordinator:
        @classmethod
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, *, logger, name, update_interval):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = {}

        def async_update_listeners(self):
            return None

    @dataclass
    class SOLARWATTItem:
        name: str
        raw: dict[str, Any]
        parsed: Any
        oh_type: str | None
        editable: bool
        label: str | None
        category: str | None

    constants = {
        "CONF_KIWIGRID_HEMS_ENABLED": "kiwigrid_hems_enabled",
        "CONF_KIWIGRID_HEMS_PASSWORD": "kiwigrid_hems_password",
        "CONF_KIWIGRID_HEMS_SCAN_INTERVAL": "kiwigrid_hems_scan_interval",
        "CONF_KIWIGRID_HEMS_USERNAME": "kiwigrid_hems_username",
        "CONF_SCAN_INTERVAL": "scan_interval",
        "DEFAULT_KIWIGRID_HEMS_SCAN_INTERVAL": 60,
        "DEFAULT_SCAN_INTERVAL": 15,
        "MAX_SCAN_INTERVAL": 3600,
        "MIN_SCAN_INTERVAL": 10,
    }

    module = load_component_module_with_stubs(
        "coordinator",
        package_name=package_name,
        stubs={
            "homeassistant": make_module("homeassistant"),
            "homeassistant.core": make_module(
                "homeassistant.core",
                HomeAssistant=object,
            ),
            "homeassistant.exceptions": make_module(
                "homeassistant.exceptions",
                ConfigEntryAuthFailed=ConfigEntryAuthFailed,
            ),
            "homeassistant.helpers": make_module("homeassistant.helpers"),
            "homeassistant.helpers.update_coordinator": make_module(
                "homeassistant.helpers.update_coordinator",
                DataUpdateCoordinator=DataUpdateCoordinator,
            ),
            f"{package_name}.client": make_module(
                f"{package_name}.client",
                SOLARWATTClient=object,
                SolarwattError=SolarwattError,
                SolarwattAuthError=SolarwattAuthError,
            ),
            f"{package_name}.const": make_module(
                f"{package_name}.const",
                **constants,
            ),
            f"{package_name}.entity_helpers": make_module(
                f"{package_name}.entity_helpers",
                detach_entityless_thing_devices=lambda *args: None,
                ensure_parent_devices_registered=lambda *args: None,
            ),
            f"{package_name}.hems_api": make_module(
                f"{package_name}.hems_api",
                item_names_to_thing_uids=lambda *args: {},
            ),
            f"{package_name}.state_parser": make_module(
                f"{package_name}.state_parser",
                SOLARWATTItem=SOLARWATTItem,
                parse_state=lambda state, pattern, item_type: state,
            ),
            f"{package_name}.thing_matching": make_module(
                f"{package_name}.thing_matching",
                canonicalize_thing_key=lambda value: str(value or ""),
                merge_thing_records=lambda current, incoming: {
                    **current,
                    **incoming,
                },
                resolve_thing_uid=lambda current, thing, uid: uid,
            ),
        },
    )
    return module, SolarwattError, SolarwattAuthError, ConfigEntryAuthFailed


coordinator_module, SolarwattError, SolarwattAuthError, ConfigEntryAuthFailed = (
    _load_coordinator_module()
)


class FakeEntry:
    def __init__(self, *, hems_enabled: bool):
        self.options = {
            "scan_interval": 15,
            "kiwigrid_hems_enabled": hems_enabled,
            "kiwigrid_hems_username": "cloud-user",
            "kiwigrid_hems_password": "cloud-password",
            "kiwigrid_hems_scan_interval": 60,
        }
        self.reauth_calls = 0

    def async_start_reauth(self, hass):
        self.reauth_calls += 1


class FakeClient:
    def __init__(self, *, local_enabled: bool = True):
        self.host = "manager.local" if local_enabled else ""
        self.username = "installer" if local_enabled else ""
        self.password = "password" if local_enabled else ""
        self.local_result: Any = [_item("local_power", "100 W")]
        self.hems_result: Any = [_item("hems_stats", "2 kWh")]
        self.flow_result: Any = [_item("hems_flow", "50 W")]
        self.local_calls = 0
        self.hems_calls = 0
        self.flow_calls = 0

    async def async_get_items(self):
        self.local_calls += 1
        return _result_or_raise(self.local_result)

    async def async_get_hems_items(self, **kwargs):
        self.hems_calls += 1
        return _result_or_raise(self.hems_result)

    async def async_get_hems_energy_flow_items(self, **kwargs):
        self.flow_calls += 1
        return _result_or_raise(self.flow_result)

def _item(name: str, state: str) -> dict[str, Any]:
    return {
        "name": name,
        "state": state,
        "type": "Number",
        "editable": False,
    }


def _result_or_raise(result):
    if isinstance(result, Exception):
        raise result
    return list(result)


def _coordinator(*, local_enabled: bool = True, hems_enabled: bool = True):
    entry = FakeEntry(hems_enabled=hems_enabled)
    client = FakeClient(local_enabled=local_enabled)
    coordinator = coordinator_module.SOLARWATTCoordinator(object(), entry, client)
    return coordinator, entry, client


def test_local_failure_keeps_hems_source_available():
    coordinator, _, client = _coordinator()
    client.local_result = SolarwattError("local unavailable")

    result = asyncio.run(coordinator._async_update_data())

    assert set(result) == {"hems_stats", "hems_flow"}
    assert coordinator.local_last_error == "local unavailable"
    assert coordinator.hems_last_error is None


def test_cached_local_data_survives_later_failure():
    coordinator, _, client = _coordinator()
    first_result = asyncio.run(coordinator._async_update_data())
    client.local_result = SolarwattError("local unavailable")
    client.flow_result = [_item("hems_flow", "60 W")]

    second_result = asyncio.run(coordinator._async_update_data())

    assert "local_power" in first_result
    assert "local_power" in second_result
    assert second_result["hems_flow"].raw["state"] == "60 W"


def test_partial_auth_failure_starts_reauth_without_hiding_cloud_data():
    coordinator, entry, client = _coordinator()
    client.local_result = SolarwattAuthError("invalid local credentials")

    result = asyncio.run(coordinator._async_update_data())

    assert set(result) == {"hems_stats", "hems_flow"}
    assert entry.reauth_calls == 1


def test_single_source_auth_failure_raises_config_entry_auth_failed():
    coordinator, entry, client = _coordinator(hems_enabled=False)
    client.local_result = SolarwattAuthError("invalid local credentials")

    with pytest.raises(ConfigEntryAuthFailed):
        asyncio.run(coordinator._async_update_data())

    assert entry.reauth_calls == 0


def test_hems_failures_are_retried_only_after_backoff(caplog):
    coordinator, _, client = _coordinator(local_enabled=False)
    client.hems_result = SolarwattError("stats unavailable")
    client.flow_result = SolarwattError("flow unavailable")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(SolarwattError):
            asyncio.run(coordinator._async_update_data())
        with pytest.raises(SolarwattError):
            asyncio.run(coordinator._async_update_data())

    assert client.hems_calls == 1
    assert client.flow_calls == 1
    assert caplog.messages.count(
        "KiwiGrid HEMS became unavailable: Unable to fetch KiwiGrid HEMS data: "
        "stats unavailable; Unable to fetch KiwiGrid HEMS energy flow: flow unavailable"
    ) == 1
