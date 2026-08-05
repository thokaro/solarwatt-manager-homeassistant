from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

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
                if name == "async_get_battery" and call_count == 2:
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
            energy_overview_to_legacy_items=lambda payload, things: [],
            kiwigrid_flow_thing=lambda: {},
            things_to_openhab_things=lambda payload: [],
        ),
    },
)


def _client():
    client = object.__new__(client_module.SOLARWATTClient)
    client._session = object()
    client.host = "manager.local"
    client._local_items_source = None
    client._local_things_source = None
    client._hems_configurator_things_cache = None
    client._hems_client = None
    client._hems_client_credentials = None
    client._hems_payload_cache = {}
    client.hems_partial_errors = ()
    client._log = logging.getLogger(__name__)
    return client


def _client_response_error(status: int):
    return client_module.ClientResponseError(
        SimpleNamespace(real_url="http://manager.local/test"),
        (),
        status=status,
        message="Not Found",
        headers={},
    )


def test_hems_poll_reuses_client_and_last_successful_endpoint_payload():
    FakeKiwiGridHEMSClient.instances.clear()
    captured_payloads.clear()
    client = _client()

    asyncio.run(client.async_get_hems_items(username="user", password="password"))
    first_battery_payload = captured_payloads[-1]["batteries"]
    asyncio.run(client.async_get_hems_items(username="user", password="password"))

    assert len(FakeKiwiGridHEMSClient.instances) == 1
    assert 1 < FakeKiwiGridHEMSClient.instances[0].max_active_requests <= 4
    assert captured_payloads[-1]["batteries"] == first_battery_payload
    assert client.hems_partial_errors == (
        "batteries: battery temporarily unavailable",
    )


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


def test_local_items_endpoint_fallback_is_cached():
    client = _client()
    rest_calls = 0
    overview_calls = 0

    async def _get_json(path, *, where):
        nonlocal rest_calls
        assert path == "/rest/items"
        rest_calls += 1
        raise _client_response_error(404)

    async def _get_energy_overview_items():
        nonlocal overview_calls
        overview_calls += 1
        return [{"name": "production"}]

    client._async_get_json_endpoint = _get_json
    client.async_get_energy_overview_items = _get_energy_overview_items

    assert asyncio.run(client.async_get_items()) == [{"name": "production"}]
    assert asyncio.run(client.async_get_items()) == [{"name": "production"}]

    assert rest_calls == 1
    assert overview_calls == 2
    assert client._local_items_source == client_module.LOCAL_ITEMS_SOURCE_ENERGY_OVERVIEW


def test_local_things_endpoint_fallback_is_cached():
    client = _client()
    configurator_calls = 0
    rest_calls = 0

    async def _get_hems_configurator_things():
        nonlocal configurator_calls
        configurator_calls += 1
        raise client_module.SolarwattProtocolError("endpoint not found")

    async def _get_json(path, *, where):
        nonlocal rest_calls
        assert path == "/rest/things"
        rest_calls += 1
        return [{"UID": "legacy-thing"}]

    client.async_get_hems_configurator_things = _get_hems_configurator_things
    client._async_get_json_endpoint = _get_json

    expected = [{"UID": "legacy-thing"}]
    assert asyncio.run(client.async_get_things()) == expected
    assert asyncio.run(client.async_get_things()) == expected

    assert configurator_calls == 1
    assert rest_calls == 2
    assert client._local_things_source == client_module.LOCAL_THINGS_SOURCE_REST


def test_energy_overview_aliases_reuse_cached_things(monkeypatch):
    client = _client()
    cached_things = [{"UID": "cached-thing"}]
    client._hems_configurator_things_cache = cached_things
    requested_paths = []
    alias_inputs = []

    async def _get_json(path, *, where):
        requested_paths.append(path)
        return {"production": 123}

    monkeypatch.setattr(
        client_module,
        "energy_overview_to_items",
        lambda payload: [{"name": "production"}],
    )

    def _legacy_items(payload, things):
        alias_inputs.append(things)
        return [{"name": "legacy_production"}]

    monkeypatch.setattr(
        client_module,
        "energy_overview_to_legacy_items",
        _legacy_items,
    )
    client._async_get_json_endpoint = _get_json

    assert asyncio.run(client.async_get_energy_overview_items()) == [
        {"name": "production"},
        {"name": "legacy_production"},
    ]
    assert requested_paths == [client_module.ENERGY_OVERVIEW_PATH]
    assert alias_inputs == [cached_things]
