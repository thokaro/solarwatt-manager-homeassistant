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
        "CONF_KIWIGRID_HEMS_SCAN_INTERVAL": "kiwigrid_hems_scan_interval",
        "CONF_KIWIGRID_FLOW_SCAN_INTERVAL": "kiwigrid_flow_scan_interval",
        "CONF_KIWIGRID_STATS_SCAN_INTERVAL": "kiwigrid_stats_scan_interval",
        "CONF_KIWIGRID_PROFILE_CACHE_INTERVAL": "kiwigrid_profile_cache_interval",
        "CONF_SCAN_INTERVAL": "scan_interval",
        "DEFAULT_KIWIGRID_HEMS_SCAN_INTERVAL": 120,
        "DEFAULT_KIWIGRID_PROFILE_CACHE_INTERVAL": 3600,
        "DEFAULT_SCAN_INTERVAL": 15,
        "MAX_SCAN_INTERVAL": 3600,
        "MIN_SCAN_INTERVAL": 10,
        "get_kiwigrid_hems_credentials": lambda options: (
            str(options.get("kiwigrid_hems_username") or "").strip(),
            str(options.get("kiwigrid_hems_password") or "").strip(),
        ),
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
            "kiwigrid_hems_username": "cloud-user" if hems_enabled else "",
            "kiwigrid_hems_password": "cloud-password" if hems_enabled else "",
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
        self.hems_partial_errors: tuple[str, ...] = ()
        self.local_calls = 0
        self.hems_calls = 0
        self.flow_calls = 0
        self.hems_requests: list[dict[str, Any]] = []

    async def async_get_energy_overview_items(self):
        self.local_calls += 1
        return _result_or_raise(self.local_result)

    async def async_get_hems_items(self, **kwargs):
        self.hems_calls += 1
        self.hems_requests.append(kwargs)
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


def test_hems_credentials_enable_cloud_polling_without_legacy_checkbox():
    coordinator, entry, client = _coordinator(local_enabled=False)
    entry.options["kiwigrid_hems_enabled"] = False

    result = asyncio.run(coordinator._async_update_data())

    assert set(result) == {"hems_stats", "hems_flow"}
    assert client.hems_calls == 1
    assert client.flow_calls == 1


def test_cached_local_data_survives_later_failure(monkeypatch):
    monkeypatch.setattr(coordinator_module.time, "monotonic", lambda: 0.0)
    coordinator, _, client = _coordinator()
    first_result = asyncio.run(coordinator._async_update_data())
    client.local_result = SolarwattError("local unavailable")
    client.flow_result = [_item("hems_flow", "60 W")]
    monkeypatch.setattr(coordinator_module.time, "monotonic", lambda: 15.0)

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


def test_hems_endpoint_partial_failure_keeps_source_available(caplog):
    coordinator, _, client = _coordinator(local_enabled=False)
    client.hems_partial_errors = (
        "analytics_finance_year: Timeout while requesting GET /v11/analytics/finance year",
    )

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(coordinator._async_update_data())

    assert set(result) == {"hems_stats", "hems_flow"}
    assert coordinator.hems_last_error is None
    assert coordinator.hems_partial_errors == client.hems_partial_errors
    assert not any("became unavailable" in message for message in caplog.messages)


def test_one_hems_subsource_failure_keeps_source_available():
    coordinator, _, client = _coordinator(local_enabled=False)
    client.hems_result = SolarwattError("stats unavailable")

    result = asyncio.run(coordinator._async_update_data())

    assert set(result) == {"hems_flow"}
    assert coordinator.hems_last_error is None
    assert coordinator.hems_partial_errors == (
        "Unable to fetch KiwiGrid HEMS data: stats unavailable",
    )


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


def test_separate_cloud_intervals_keep_local_updates_fast(monkeypatch):
    now = 0.0
    monkeypatch.setattr(coordinator_module.time, "monotonic", lambda: now)
    entry = FakeEntry(hems_enabled=True)
    entry.options.update({
        "kiwigrid_hems_scan_interval": 120,
        "kiwigrid_flow_scan_interval": 30,
        "kiwigrid_stats_scan_interval": 300,
        "kiwigrid_profile_cache_interval": 1800,
    })
    client = FakeClient()
    coordinator = coordinator_module.SOLARWATTCoordinator(object(), entry, client)

    for tick in range(0, 301, 15):
        now = float(tick)
        result = asyncio.run(coordinator._async_update_data())
        assert set(result) == {"local_power", "hems_stats", "hems_flow"}

    assert client.local_calls == 21
    assert client.flow_calls == 11
    assert [(request["refresh_devices"], request["refresh_statistics"])
            for request in client.hems_requests] == [
        (True, True), (True, False), (True, False), (False, True),
    ]
    assert all(request["profile_cache_interval"] == 1800 for request in client.hems_requests)


def test_cloud_can_poll_faster_than_local_devices(monkeypatch):
    now = 0.0
    monkeypatch.setattr(coordinator_module.time, "monotonic", lambda: now)
    entry = FakeEntry(hems_enabled=True)
    entry.options.update({
        "scan_interval": 60,
        "kiwigrid_hems_scan_interval": 120,
        "kiwigrid_flow_scan_interval": 15,
        "kiwigrid_stats_scan_interval": 30,
    })
    client = FakeClient()
    coordinator = coordinator_module.SOLARWATTCoordinator(object(), entry, client)

    for tick in (0, 15, 30):
        now = float(tick)
        asyncio.run(coordinator._async_update_data())

    assert coordinator.update_interval.total_seconds() == 15
    assert client.local_calls == 1
    assert client.flow_calls == 3
    assert [(request["refresh_devices"], request["refresh_statistics"])
            for request in client.hems_requests] == [(True, True), (False, True)]


def test_legacy_options_keep_custom_flow_and_statistics_intervals(monkeypatch):
    now = 0.0
    monkeypatch.setattr(coordinator_module.time, "monotonic", lambda: now)
    entry = FakeEntry(hems_enabled=True)
    entry.options.update({"scan_interval": 30, "kiwigrid_hems_scan_interval": 90})
    client = FakeClient()
    coordinator = coordinator_module.SOLARWATTCoordinator(object(), entry, client)

    for tick in (0, 30, 60, 90):
        now = float(tick)
        asyncio.run(coordinator._async_update_data())

    assert client.local_calls == 4
    assert client.flow_calls == 4
    assert client.hems_calls == 2
    assert all(request["refresh_statistics"] for request in client.hems_requests)
    assert all(request["profile_cache_interval"] == 3600 for request in client.hems_requests)


def test_flow_failure_respects_backoff_and_invalidation(monkeypatch):
    now = 0.0
    monkeypatch.setattr(coordinator_module.time, "monotonic", lambda: now)
    entry = FakeEntry(hems_enabled=True)
    entry.options.update({
        "kiwigrid_flow_scan_interval": 30,
        "kiwigrid_stats_scan_interval": 300,
    })
    client = FakeClient()
    coordinator = coordinator_module.SOLARWATTCoordinator(object(), entry, client)
    asyncio.run(coordinator._async_update_data())
    client.flow_result = SolarwattError("flow unavailable")

    for tick in (30, 45, 60, 75):
        now = float(tick)
        asyncio.run(coordinator._async_update_data())
    assert client.flow_calls == 2

    now = 90.0
    asyncio.run(coordinator._async_update_data())
    assert client.flow_calls == 3
    coordinator.invalidate_hems_cache()
    client.flow_result = [_item("hems_flow", "70 W")]
    result = asyncio.run(coordinator._async_update_data())

    assert result["hems_flow"].raw["state"] == "70 W"
    assert client.flow_calls == 4
    assert client.hems_requests[-1]["refresh_devices"]
    assert client.hems_requests[-1]["refresh_statistics"]


def test_failed_statistics_do_not_retry_on_device_only_polls(monkeypatch):
    now = 0.0
    monkeypatch.setattr(coordinator_module.time, "monotonic", lambda: now)
    entry = FakeEntry(hems_enabled=True)
    entry.options["kiwigrid_stats_scan_interval"] = 300
    client = FakeClient()
    coordinator = coordinator_module.SOLARWATTCoordinator(object(), entry, client)
    client.hems_result = SolarwattError("endpoints unavailable")

    for tick in (0, 15, 60, 120, 300):
        now = float(tick)
        asyncio.run(coordinator._async_update_data())

    assert [(request["refresh_devices"], request["refresh_statistics"])
            for request in client.hems_requests] == [
        (True, True), (True, False), (True, False), (True, True),
    ]
