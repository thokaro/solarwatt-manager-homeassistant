from __future__ import annotations

import asyncio
import logging

import pytest

from .module_loader import (
    load_component_module,
    load_component_module_with_stubs,
    make_module,
)


class FakeKiwiGridHEMSError(Exception):
    pass


class FakeKiwiGridHEMSAuthError(FakeKiwiGridHEMSError):
    pass


class FakeKiwiGridHEMSConnectionError(FakeKiwiGridHEMSError):
    pass


class FakeKiwiGridHEMSProtocolError(FakeKiwiGridHEMSError):
    pass


class FakeKiwiGridHEMSClient:
    instances: list["FakeKiwiGridHEMSClient"] = []

    def __init__(self, session, *, username="", password="", **kwargs):
        self.enabled = bool(username and password)
        self.calls: dict[str, int] = {}
        self.active_requests = 0
        self.max_active_requests = 0
        self.fail_all = False
        self.persistent_battery_failure = False
        self.instances.append(self)

    async def async_ensure_authenticated(self):
        self.calls["authenticate"] = self.calls.get("authenticate", 0) + 1

    def __getattr__(self, name):
        if not name.startswith("async_"):
            raise AttributeError(name)

        async def _endpoint(**kwargs):
            call_count = self.calls.get(name, 0) + 1
            self.calls[name] = call_count
            self.active_requests += 1
            self.max_active_requests = max(
                self.max_active_requests,
                self.active_requests,
            )
            try:
                await asyncio.sleep(0)
                if self.fail_all:
                    raise FakeKiwiGridHEMSConnectionError(
                        f"{name} temporarily unavailable"
                    )
                if name == "async_get_battery" and (
                    call_count == 2 or self.persistent_battery_failure
                ):
                    raise FakeKiwiGridHEMSConnectionError(
                        "battery temporarily unavailable"
                    )
                if name.startswith("async_get_analytics_finance"):
                    return {
                        "timeseries": [
                            {"id": "cost", "aggregated": float(call_count)},
                        ]
                    }
                return [{"endpoint": name, "call": call_count}]
            finally:
                self.active_requests -= 1

        return _endpoint


captured_payloads: list[dict] = []
captured_name_payloads: list[dict] = []


def _hems_payloads_to_items(**payloads):
    captured_payloads.append(payloads)
    return []


def _hems_device_names_by_id(**payloads):
    captured_name_payloads.append(payloads)
    return {}


hems_client = load_component_module("hems_client")

PACKAGE_NAME = "solarwatt_manager_client_polling_test"
client_module = load_component_module_with_stubs(
    "client",
    package_name=PACKAGE_NAME,
    stubs={
        "homeassistant": make_module("homeassistant"),
        "homeassistant.helpers": make_module("homeassistant.helpers"),
        "homeassistant.helpers.update_coordinator": make_module(
            "homeassistant.helpers.update_coordinator",
            UpdateFailed=Exception,
        ),
        f"{PACKAGE_NAME}.hems_client": make_module(
            f"{PACKAGE_NAME}.hems_client",
            KiwiGridHEMSAuthError=FakeKiwiGridHEMSAuthError,
            KiwiGridHEMSClient=FakeKiwiGridHEMSClient,
            KiwiGridHEMSConnectionError=FakeKiwiGridHEMSConnectionError,
            KiwiGridHEMSError=FakeKiwiGridHEMSError,
            KiwiGridHEMSProtocolError=FakeKiwiGridHEMSProtocolError,
            consumers_endpoint_to_items=lambda payload: [],
            energy_flow_endpoint_to_items=lambda payload, **kwargs: [],
            hems_device_names_by_id=_hems_device_names_by_id,
            hems_payloads_to_items=_hems_payloads_to_items,
            hems_payloads_to_things=lambda **payloads: [],
            is_analytics_payload=hems_client.is_analytics_payload,
            merge_analytics_aggregates=hems_client.merge_analytics_aggregates,
            summary_anchor_time_window=hems_client.summary_anchor_time_window,
        ),
        f"{PACKAGE_NAME}.hems_api": make_module(
            f"{PACKAGE_NAME}.hems_api",
            ENERGY_OVERVIEW_PATH="/energy-overview",
            THINGS_PATH="/things",
            energy_overview_to_items=lambda payload: [],
            hems_configurator_to_things=lambda payload: [],
            kiwigrid_flow_thing=lambda: {},
        ),
    },
)


def _client():
    client = object.__new__(client_module.SOLARWATTClient)
    client._session = object()
    client.host = "manager.local"
    client._hems_client = None
    client._hems_client_credentials = None
    client._hems_payload_cache = {}
    client._hems_summary_anchors = {}
    client._hems_profile_updated_at = None
    client._hems_endpoint_errors = {}
    client.hems_partial_errors = ()
    client._log = logging.getLogger(__name__)
    return client


def test_hems_poll_retries_one_transient_endpoint_sequentially():
    FakeKiwiGridHEMSClient.instances.clear()
    captured_payloads.clear()
    client = _client()

    asyncio.run(client.async_get_hems_items(username="user", password="password"))
    asyncio.run(client.async_get_hems_items(username="user", password="password"))

    hems = FakeKiwiGridHEMSClient.instances[0]
    assert len(FakeKiwiGridHEMSClient.instances) == 1
    assert 1 < hems.max_active_requests <= 4
    assert hems.calls["async_get_battery"] == 3
    assert hems.calls["async_get_analytics_consumption_year"] == 2
    assert captured_payloads[-1]["batteries"] == [
        {"endpoint": "async_get_battery", "call": 3}
    ]
    assert client.hems_partial_errors == ()


def test_hems_poll_reuses_cache_after_sequential_retry_fails():
    FakeKiwiGridHEMSClient.instances.clear()
    captured_payloads.clear()
    client = _client()

    asyncio.run(client.async_get_hems_items(username="user", password="password"))
    first_battery_payload = captured_payloads[-1]["batteries"]
    hems = FakeKiwiGridHEMSClient.instances[0]
    hems.persistent_battery_failure = True

    asyncio.run(client.async_get_hems_items(username="user", password="password"))

    assert hems.calls["async_get_battery"] == 3
    assert captured_payloads[-1]["batteries"] == first_battery_payload
    assert client.hems_partial_errors == (
        "batteries: battery temporarily unavailable",
    )


def test_hems_poll_skips_retries_and_fails_when_all_endpoints_are_unavailable():
    FakeKiwiGridHEMSClient.instances.clear()
    client = _client()
    hems = client._get_hems_client("user", "password")
    hems.fail_all = True

    with pytest.raises(
        client_module.SolarwattConnectionError,
        match="All requested KiwiGrid HEMS endpoints failed",
    ):
        asyncio.run(client.async_get_hems_items(username="user", password="password"))

    assert hems.calls["async_get_battery"] == 1


def test_flow_poll_reuses_cached_device_metadata():
    FakeKiwiGridHEMSClient.instances.clear()
    captured_name_payloads.clear()
    client = _client()

    asyncio.run(client.async_get_hems_items(username="user", password="password"))
    hems = FakeKiwiGridHEMSClient.instances[0]
    device_calls_before = hems.calls["async_get_devices"]

    asyncio.run(
        client.async_get_hems_energy_flow_items(
            username="user",
            password="password",
        )
    )

    assert hems.calls["async_get_devices"] == device_calls_before
    assert captured_name_payloads[-1]["devices"] == client._hems_payload_cache[
        "devices"
    ]


def test_initial_thing_discovery_can_reuse_poll_payloads():
    FakeKiwiGridHEMSClient.instances.clear()
    client = _client()

    asyncio.run(client.async_get_hems_items(username="user", password="password"))
    hems = FakeKiwiGridHEMSClient.instances[0]
    endpoint_calls_before = dict(hems.calls)

    asyncio.run(
        client.async_get_hems_things(
            username="user",
            password="password",
            include_energy_flow=True,
            use_cached=True,
        )
    )

    assert hems.calls == endpoint_calls_before


def test_energy_overview_returns_only_canonical_items(monkeypatch):
    client = _client()
    requested_paths = []

    async def _get_json(path, *, where):
        requested_paths.append(path)
        return {"production": 123}

    monkeypatch.setattr(
        client_module,
        "energy_overview_to_items",
        lambda payload: [{"name": "production"}],
    )
    client._async_get_json_endpoint = _get_json

    assert asyncio.run(client.async_get_energy_overview_items()) == [
        {"name": "production"}
    ]
    assert requested_paths == [client_module.ENERGY_OVERVIEW_PATH]


def test_local_things_use_only_hems_configurator_endpoint():
    client = _client()
    calls = 0

    async def _get_hems_configurator_things():
        nonlocal calls
        calls += 1
        return [{"UID": "current-thing"}]

    client.async_get_hems_configurator_things = _get_hems_configurator_things

    assert asyncio.run(client.async_get_things()) == [{"UID": "current-thing"}]
    assert calls == 1


def test_device_only_poll_reuses_all_statistics_payloads(monkeypatch):
    client = _client()
    kwargs = {"username": "user", "password": "password", "profile_cache_interval": 3600}
    asyncio.run(client.async_get_hems_items(**kwargs))
    hems = client._hems_client
    previous = captured_payloads[-1]
    before = dict(hems.calls)

    asyncio.run(client.async_get_hems_items(**kwargs, refresh_statistics=False))

    for name, calls in before.items():
        if name.startswith("async_get_analytics") or name == "async_get_user_profile":
            assert hems.calls[name] == calls
    for key, payload in previous.items():
        if key.startswith("analytics_"):
            assert captured_payloads[-1][key] is payload
    assert hems.calls["async_get_devices"] == before["async_get_devices"] + 1


def test_statistics_only_poll_reuses_device_payloads():
    client = _client()
    kwargs = {"username": "user", "password": "password", "profile_cache_interval": 3600}
    asyncio.run(client.async_get_hems_items(**kwargs))
    hems = client._hems_client
    previous = captured_payloads[-1]
    before = dict(hems.calls)

    asyncio.run(client.async_get_hems_items(**kwargs, refresh_devices=False))

    assert hems.calls["async_get_devices"] == before["async_get_devices"]
    assert hems.calls["async_get_battery"] == before["async_get_battery"]
    assert hems.calls["async_get_user_profile"] == 1
    assert hems.calls["async_get_analytics_consumption_year"] == 2
    assert captured_payloads[-1]["devices"] is previous["devices"]
    assert captured_payloads[-1]["batteries"] is previous["batteries"]


def test_profile_cache_expires_at_configured_duration(monkeypatch):
    now = 0.0
    monkeypatch.setattr(client_module.time, "monotonic", lambda: now)
    client = _client()
    kwargs = {"username": "user", "password": "password", "profile_cache_interval": 600}
    asyncio.run(client.async_get_hems_items(**kwargs))
    hems = client._hems_client
    profile = captured_payloads[-1]["user_profile"]

    now = 599.0
    asyncio.run(client.async_get_hems_items(**kwargs))
    assert hems.calls["async_get_user_profile"] == 1
    assert captured_payloads[-1]["user_profile"] is profile

    now = 600.0
    asyncio.run(client.async_get_hems_items(**kwargs))
    assert hems.calls["async_get_user_profile"] == 2
    assert captured_payloads[-1]["user_profile"] != profile


def test_expired_profile_failure_keeps_cache_and_retries_later(monkeypatch):
    now = 0.0
    monkeypatch.setattr(client_module.time, "monotonic", lambda: now)
    client = _client()
    kwargs = {"username": "user", "password": "password", "profile_cache_interval": 600}
    asyncio.run(client.async_get_hems_items(**kwargs))
    hems = client._hems_client
    profile = captured_payloads[-1]["user_profile"]
    original_getter = hems.async_get_user_profile

    async def failed_profile():
        raise FakeKiwiGridHEMSConnectionError("profile unavailable")

    monkeypatch.setattr(hems, "async_get_user_profile", failed_profile)
    now = 600.0
    asyncio.run(client.async_get_hems_items(**kwargs))
    assert captured_payloads[-1]["user_profile"] is profile
    assert client._hems_profile_updated_at == 0.0
    assert "user_profile: profile unavailable" in client.hems_partial_errors

    monkeypatch.setattr(hems, "async_get_user_profile", original_getter)
    now = 720.0
    asyncio.run(client.async_get_hems_items(**kwargs))
    assert client._hems_profile_updated_at == 720.0
    assert not client.hems_partial_errors
    assert captured_payloads[-1]["user_profile"] != profile


def test_cached_profile_does_not_mask_portal_outage():
    client = _client()
    kwargs = {"username": "user", "password": "password", "profile_cache_interval": 3600}
    asyncio.run(client.async_get_hems_items(**kwargs))
    hems = client._hems_client
    hems.fail_all = True

    with pytest.raises(client_module.SolarwattConnectionError):
        asyncio.run(client.async_get_hems_items(**kwargs))
    assert hems.calls["async_get_user_profile"] == 1


def test_credentials_change_clears_profile_cache_and_endpoint_errors():
    client = _client()
    asyncio.run(client.async_get_hems_items(
        username="first", password="password", profile_cache_interval=3600,
    ))
    old_hems = client._hems_client
    client._hems_endpoint_errors["devices"] = "devices: unavailable"

    asyncio.run(client.async_get_hems_items(
        username="second", password="password", profile_cache_interval=3600,
    ))

    assert client._hems_client is not old_hems
    assert client._hems_client.calls["async_get_user_profile"] == 1
    assert not client.hems_partial_errors


def test_unpolled_statistics_keep_partial_errors_until_recovery(monkeypatch):
    client = _client()
    kwargs = {"username": "user", "password": "password", "profile_cache_interval": 3600}
    hems = client._get_hems_client("user", "password")
    original_getter = hems.async_get_analytics_finance

    async def malformed_finance():
        return {"unexpected": True}

    monkeypatch.setattr(hems, "async_get_analytics_finance", malformed_finance)
    asyncio.run(client.async_get_hems_items(**kwargs))
    errors = client.hems_partial_errors
    assert any("analytics_finance:" in error for error in errors)

    asyncio.run(client.async_get_hems_items(**kwargs, refresh_statistics=False))
    assert client.hems_partial_errors == errors

    monkeypatch.setattr(hems, "async_get_analytics_finance", original_getter)
    asyncio.run(client.async_get_hems_items(**kwargs, refresh_devices=False))
    assert not client.hems_partial_errors
    assert captured_payloads[-1]["analytics_finance_year"]


def test_flow_recovery_clears_errors_from_discovery(monkeypatch):
    client = _client()
    hems = client._get_hems_client("user", "password")
    original_getter = hems.async_get_energy_flow

    async def failed_flow():
        raise FakeKiwiGridHEMSConnectionError("flow unavailable")

    monkeypatch.setattr(hems, "async_get_energy_flow", failed_flow)
    asyncio.run(client.async_get_hems_items(
        username="user", password="password", include_energy_flow=True,
    ))
    assert "energy_flow: flow unavailable" in client.hems_partial_errors

    monkeypatch.setattr(hems, "async_get_energy_flow", original_getter)
    asyncio.run(client.async_get_hems_energy_flow_items(username="user", password="password"))
    asyncio.run(client.async_get_hems_items(username="user", password="password"))

    assert not client.hems_partial_errors
