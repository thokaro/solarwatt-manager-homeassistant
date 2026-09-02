from __future__ import annotations

import asyncio
import logging

import pytest

from .module_loader import load_component_module_with_stubs, make_module


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
