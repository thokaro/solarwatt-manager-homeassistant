from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

import pytest

from .module_loader import (
    load_component_module,
    load_component_module_with_stubs,
    make_module,
)

hems_client = load_component_module("hems_client")

TODAY_COST = 1.5
ANCHOR_COSTS = {
    "async_get_analytics_finance_month": 10.0,
    "async_get_analytics_finance_year": 100.0,
}
MID_PERIOD = datetime(2026, 9, 15, 14, 5).astimezone()
FIRST_OF_MONTH = datetime(2026, 9, 1, 8, 30).astimezone()
FIRST_OF_YEAR = datetime(2026, 1, 1, 8, 30).astimezone()


def _analytics_payload(cost: float) -> dict:
    return {
        "timeseries": [
            {"id": "cost", "name": "Cost", "unit": "CURRENCY", "aggregated": cost},
        ]
    }


class FakeHEMSError(Exception):
    pass


class FakeHEMSConnectionError(FakeHEMSError):
    pass


class FakeHEMSClient:
    """HEMS stub that answers analytics endpoints and records their ranges."""

    instances: list["FakeHEMSClient"] = []

    def __init__(self, session, *, username="", password="", **kwargs):
        self.enabled = bool(username and password)
        self.calls: dict[str, int] = {}
        self.ranges: dict[str, list[tuple]] = {}
        self.failing: set[str] = set()
        self.empty: set[str] = set()
        self.malformed: set[str] = set()
        self.fail_all = False
        self.today_cost = TODAY_COST
        self.instances.append(self)

    async def async_ensure_authenticated(self):
        return None

    def __getattr__(self, name):
        if not name.startswith("async_"):
            raise AttributeError(name)

        async def _endpoint(**kwargs):
            self.calls[name] = self.calls.get(name, 0) + 1
            if self.fail_all or name in self.failing:
                raise FakeHEMSConnectionError(f"{name} unavailable")
            if name in self.malformed:
                return {"unexpected": True}
            if not name.startswith("async_get_analytics"):
                return []
            self.ranges.setdefault(name, []).append(
                (kwargs.get("from_time"), kwargs.get("to_time"))
            )
            if name in self.empty:
                return {"timeseries": []}
            return _analytics_payload(
                ANCHOR_COSTS.get(name, self.today_cost)
            )

        return _endpoint


captured_payloads: list[dict] = []


def _capture_payloads(**payloads):
    captured_payloads.append(payloads)
    return []


PACKAGE_NAME = "solarwatt_manager_summary_anchor_test"
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
            KiwiGridHEMSAuthError=type("FakeAuthError", (FakeHEMSError,), {}),
            KiwiGridHEMSClient=FakeHEMSClient,
            KiwiGridHEMSConnectionError=FakeHEMSConnectionError,
            KiwiGridHEMSError=FakeHEMSError,
            KiwiGridHEMSProtocolError=type("FakeProtocolError", (FakeHEMSError,), {}),
            consumers_endpoint_to_items=lambda payload: [],
            energy_flow_endpoint_to_items=lambda payload, **kwargs: [],
            hems_device_names_by_id=lambda **payloads: {},
            hems_payloads_to_items=_capture_payloads,
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


def _frozen_datetime(moment: datetime) -> type[datetime]:
    """Return a datetime subclass whose now() is pinned to one moment."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    return _Frozen


@pytest.fixture
def at_time(monkeypatch):
    """Pin the client's clock so the tests do not depend on today's date."""

    def _pin(moment: datetime) -> datetime:
        monkeypatch.setattr(client_module, "datetime", _frozen_datetime(moment))
        return moment

    return _pin


@pytest.fixture(autouse=True)
def _reset_state():
    FakeHEMSClient.instances.clear()
    captured_payloads.clear()
    yield


def _client():
    client = object.__new__(client_module.SOLARWATTClient)
    client._session = object()
    client.host = ""
    client._hems_client = None
    client._hems_client_credentials = None
    client._hems_payload_cache = {}
    client._hems_summary_anchors = {}
    client.hems_partial_errors = ()
    client._log = logging.getLogger(__name__)
    return client


def _poll(client):
    captured_payloads.clear()
    asyncio.run(client.async_get_hems_items(username="user", password="password"))
    return captured_payloads[-1]


def _aggregate(payload) -> float:
    return payload["timeseries"][0]["aggregated"]


def _wall_clock(window):
    """Return the window as naive local times, the way the API receives it."""
    return tuple(value.replace(tzinfo=None) for value in window)


def test_summary_payloads_add_today_to_the_completed_days(at_time):
    at_time(MID_PERIOD)
    payloads = _poll(_client())

    assert _aggregate(payloads["analytics_finance"]) == TODAY_COST
    assert _aggregate(payloads["analytics_finance_month"]) == 10.0 + TODAY_COST
    assert _aggregate(payloads["analytics_finance_year"]) == 100.0 + TODAY_COST


def test_summary_anchor_requests_only_completed_days(at_time):
    at_time(MID_PERIOD)
    _poll(_client())

    hems = FakeHEMSClient.instances[0]
    for name in ANCHOR_COSTS:
        _from_time, to_time = hems.ranges[name][0]
        assert to_time.replace(tzinfo=None) == datetime(2026, 9, 14, 23, 59, 59)


def test_summary_anchor_is_fetched_once_per_day(at_time):
    at_time(MID_PERIOD)
    client = _client()
    _poll(client)

    hems = FakeHEMSClient.instances[0]
    hems.today_cost = 4.0
    second = _poll(client)

    for name in ANCHOR_COSTS:
        assert hems.calls[name] == 1
    assert hems.calls["async_get_analytics_finance"] == 2
    # The anchor comes from cache while the total still follows today.
    assert _aggregate(second["analytics_finance_year"]) == 100.0 + 4.0


def test_first_day_of_the_period_reports_today_without_an_anchor_request(at_time):
    at_time(FIRST_OF_MONTH)
    payloads = _poll(_client())

    hems = FakeHEMSClient.instances[0]
    assert "async_get_analytics_finance_month" not in hems.calls
    assert _aggregate(payloads["analytics_finance_month"]) == TODAY_COST
    # The year still has completed days on the first of a month.
    assert _aggregate(payloads["analytics_finance_year"]) == 100.0 + TODAY_COST


def test_first_day_of_the_year_reports_today_for_both_ranges(at_time):
    at_time(FIRST_OF_YEAR)
    payloads = _poll(_client())

    hems = FakeHEMSClient.instances[0]
    assert not any(name in hems.calls for name in ANCHOR_COSTS)
    assert _aggregate(payloads["analytics_finance_month"]) == TODAY_COST
    assert _aggregate(payloads["analytics_finance_year"]) == TODAY_COST


def test_summary_anchor_is_refreshed_after_a_calendar_day(at_time):
    at_time(MID_PERIOD)
    client = _client()
    _poll(client)

    at_time(MID_PERIOD + timedelta(days=1))
    hems = FakeHEMSClient.instances[0]
    hems.today_cost = 2.5
    payloads = _poll(client)

    assert hems.calls["async_get_analytics_finance_year"] == 2
    _from_time, to_time = hems.ranges["async_get_analytics_finance_year"][1]
    assert to_time.replace(tzinfo=None) == datetime(2026, 9, 15, 23, 59, 59)
    assert _aggregate(payloads["analytics_finance_year"]) == 100.0 + 2.5


def test_failed_anchor_keeps_the_previous_total_without_adding_today_twice(at_time):
    at_time(MID_PERIOD)
    client = _client()
    _poll(client)

    # The next day the anchor is due again, and its request fails.
    at_time(MID_PERIOD + timedelta(days=1))
    hems = FakeHEMSClient.instances[0]
    hems.failing.add("async_get_analytics_finance_year")
    payloads = _poll(client)

    assert _aggregate(payloads["analytics_finance_year"]) == 100.0 + TODAY_COST


def test_failed_today_payload_keeps_the_previous_total(at_time):
    at_time(MID_PERIOD)
    client = _client()
    _poll(client)

    hems = FakeHEMSClient.instances[0]
    hems.failing.add("async_get_analytics_finance")
    payloads = _poll(client)

    assert _aggregate(payloads["analytics_finance_year"]) == 100.0 + TODAY_COST
    assert _aggregate(payloads["analytics_finance_month"]) == 10.0 + TODAY_COST


def test_anchor_without_today_is_never_published_on_its_own(at_time):
    at_time(MID_PERIOD)
    client = _client()

    # First poll ever: the anchor succeeds but today fails, so no total exists.
    hems = FakeHEMSClient(None, username="user", password="password")
    hems.failing.add("async_get_analytics_finance")
    client._hems_client = hems
    client._hems_client_credentials = ("user", "password")
    payloads = _poll(client)

    assert hems.calls["async_get_analytics_finance_month"] == 1
    # Publishing the bare anchor would report the month without today's cost.
    assert not payloads["analytics_finance_month"]
    assert "analytics_finance_month" not in client._hems_payload_cache


def test_anchor_without_series_reports_today_alone(at_time):
    at_time(MID_PERIOD)
    client = _client()
    hems = FakeHEMSClient(None, username="user", password="password")
    hems.empty.add("async_get_analytics_finance_year")
    client._hems_client = hems
    client._hems_client_credentials = ("user", "password")
    payloads = _poll(client)

    # A range that carries no series is valid data, not a failure: the account
    # has nothing for the completed days, so the year is today.
    assert _aggregate(payloads["analytics_finance_year"]) == TODAY_COST
    assert "analytics_finance_year" in client._hems_summary_anchors
    assert not client.hems_partial_errors


def test_malformed_anchor_keeps_the_previous_total(at_time):
    at_time(MID_PERIOD)
    client = _client()
    _poll(client)

    at_time(MID_PERIOD + timedelta(days=1))
    hems = FakeHEMSClient.instances[0]
    hems.malformed.add("async_get_analytics_finance_year")
    payloads = _poll(client)

    assert _aggregate(payloads["analytics_finance_year"]) == 100.0 + TODAY_COST
    # The stale anchor stays put but is not carried forward to the new day.
    assert client._hems_summary_anchors["analytics_finance_year"][0] == date(
        2026, 9, 14
    )


def test_cached_anchors_do_not_mask_a_complete_portal_outage(at_time):
    at_time(MID_PERIOD)
    client = _client()
    _poll(client)

    hems = FakeHEMSClient.instances[0]
    hems.fail_all = True
    with pytest.raises(client_module.SolarwattConnectionError):
        asyncio.run(client.async_get_hems_items(username="user", password="password"))


def test_day_rollover_during_a_poll_does_not_recombine(at_time):
    at_time(MID_PERIOD)
    client = _client()
    payloads = _poll(client)
    combined = payloads["analytics_finance_year"]

    # A poll that started yesterday must not merge into today's halves.
    stale = {
        "analytics_finance_year": _analytics_payload(500.0),
        "analytics_finance_month": _analytics_payload(50.0),
        "analytics_finance": _analytics_payload(9.0),
    }
    client._apply_summary_anchors(
        stale,
        set(stale),
        MID_PERIOD - timedelta(days=1),
    )

    assert stale["analytics_finance_year"] == combined


def test_summary_anchor_time_window_skips_the_first_day_of_the_period():
    assert hems_client.summary_anchor_time_window("month", now=FIRST_OF_MONTH) is None
    assert hems_client.summary_anchor_time_window("year", now=FIRST_OF_YEAR) is None
    assert _wall_clock(
        hems_client.summary_anchor_time_window("year", now=FIRST_OF_MONTH)
    ) == (datetime(2026, 1, 1), datetime(2026, 8, 31, 23, 59, 59))


def test_summary_anchor_time_window_covers_the_completed_days():
    assert _wall_clock(
        hems_client.summary_anchor_time_window("month", now=MID_PERIOD)
    ) == (datetime(2026, 9, 1), datetime(2026, 9, 14, 23, 59, 59))


def test_merge_analytics_aggregates_falls_back_to_a_single_side():
    payload = _analytics_payload(2.0)

    assert hems_client.merge_analytics_aggregates(None, payload) == payload
    assert hems_client.merge_analytics_aggregates(payload, None) == payload
    assert hems_client.merge_analytics_aggregates(None, None) is None


def test_merge_analytics_aggregates_keeps_series_missing_from_the_anchor():
    anchor = _analytics_payload(2.0)
    increment = {
        "timeseries": [
            {"id": "cost", "aggregated": 1.0},
            {"id": "feed_in_revenue", "aggregated": 4.0},
        ]
    }

    merged = hems_client.merge_analytics_aggregates(anchor, increment)

    assert [series["aggregated"] for series in merged["timeseries"]] == [3.0, 4.0]


def test_merge_analytics_aggregates_matches_series_by_id_before_name():
    anchor = {"timeseries": [{"id": "grid~cost", "name": "cost", "aggregated": 2.0}]}
    increment = {"timeseries": [{"id": "grid~cost", "name": "Cost", "aggregated": 1.0}]}

    merged = hems_client.merge_analytics_aggregates(anchor, increment)

    assert len(merged["timeseries"]) == 1
    assert merged["timeseries"][0]["aggregated"] == 3.0


def test_merge_analytics_aggregates_ignores_non_numeric_aggregates():
    anchor = _analytics_payload(2.0)
    increment = {"timeseries": [{"id": "cost", "aggregated": None}]}

    merged = hems_client.merge_analytics_aggregates(anchor, increment)

    assert merged["timeseries"][0]["aggregated"] == 2.0
