from __future__ import annotations

import json

import pytest

from .module_loader import load_component_module

stats_total_state = load_component_module("stats_total_state")
StatsTotalState = stats_total_state.StatsTotalState


def test_stats_total_state_adds_previous_year_at_calendar_year_rollover():
    state = StatsTotalState()

    assert state.value_with_offset("source", 100.0, calendar_year=2025) == 100.0
    assert state.value_with_offset("source", 150.0, calendar_year=2025) == 150.0
    assert state.value_with_offset("source", 0.0, calendar_year=2026) == 150.0
    assert state.value_with_offset("source", 25.0, calendar_year=2026) == 175.0


def test_stats_total_state_does_not_roll_over_when_value_falls_within_year():
    state = StatsTotalState()

    assert state.value_with_offset("source", 3000.0, calendar_year=2026) == 3000.0
    assert state.value_with_offset("source", 0.0, calendar_year=2026) == 3000.0
    assert state.value_with_offset("source", 3000.0, calendar_year=2026) == 3000.0
    assert state.value_with_offset("source", 3005.0, calendar_year=2026) == 3005.0


def test_stats_total_state_holds_daily_corrections_until_the_total_catches_up():
    state = StatsTotalState(offsets={"source": 500.0})

    assert state.value_with_offset("source", 1000.0, calendar_year=2026) == 1500.0
    assert state.value_with_offset("source", 990.0, calendar_year=2026) == 1500.0
    assert state.value_with_offset("source", 995.0, calendar_year=2026) == 1500.0
    assert state.value_with_offset("source", 1002.0, calendar_year=2026) == 1502.0
    assert state.offset("source") == 500.0


def test_stats_total_state_carries_correction_across_year_rollover():
    state = StatsTotalState()

    assert state.value_with_offset("source", 1000.0, calendar_year=2026) == 1000.0
    assert state.value_with_offset("source", 990.0, calendar_year=2026) == 1000.0
    assert state.value_with_offset("source", 0.0, calendar_year=2027) == 1000.0
    assert state.value_with_offset("source", 5.0, calendar_year=2027) == 1000.0
    assert state.value_with_offset("source", 12.0, calendar_year=2027) == 1002.0
    assert state.sources["source"]["base"] == 990.0


def test_stats_total_state_restores_high_water_and_corrected_raw_value():
    state = StatsTotalState(offsets={"source": 500.0})
    state.value_with_offset("source", 1000.0, calendar_year=2026)
    state.value_with_offset("source", 990.0, calendar_year=2026)
    saved = json.loads(json.dumps({"sources": state.sources, "offsets": state.offsets}))
    restored = StatsTotalState(
        sources=stats_total_state.float_records(saved["sources"]),
        offsets=stats_total_state.float_values(saved["offsets"]),
    )

    assert restored.value_with_offset("source", 995.0, calendar_year=2026) == 1500.0
    assert restored.value_with_offset("source", 0.0, calendar_year=2027) == 1500.0
    assert restored.value_with_offset("source", 10.0, calendar_year=2027) == 1505.0


def test_stats_total_state_initializes_high_water_from_existing_record():
    state = StatsTotalState(
        sources={"source": {"base": 100.0, "last": 1000.0, "year": 2026.0}},
    )

    assert state.value_with_offset("source", 990.0, calendar_year=2026) == 1100.0
    assert state.sources["source"]["last"] == 990.0
    assert state.dirty


def test_stats_total_state_keeps_sources_independent():
    state = StatsTotalState()

    assert state.value_with_offset("first", 1000.0, calendar_year=2026) == 1000.0
    assert state.value_with_offset("second", 50.0, calendar_year=2026) == 50.0
    assert state.value_with_offset("first", 990.0, calendar_year=2026) == 1000.0
    assert state.value_with_offset("second", 60.0, calendar_year=2026) == 60.0


def test_stats_total_state_initializes_year_for_legacy_record_without_rollover():
    state = StatsTotalState(sources={"source": {"base": 100.0, "last": 3000.0}})

    assert state.value_with_offset("source", 0.0, calendar_year=2026) == 3100.0
    assert state.sources["source"]["base"] == 100.0
    assert state.sources["source"]["year"] == 2026


def test_stats_total_state_stores_offset_from_desired_value():
    state = StatsTotalState()

    assert state.calculated_value("source", 200.0) == 200.0
    assert state.set_desired_value("source", 250.0, 200.0) == 50.0
    assert state.value_with_offset("source", 225.0) == 275.0


def test_stats_total_state_can_set_and_reset_direct_offset():
    state = StatsTotalState()

    state.set_offset("source", 12.5)
    assert state.value_with_offset("source", 100.0) == 112.5

    state.reset_offset("source")
    assert state.value_with_offset("source", 100.0) == 100.0


def test_stats_total_state_rejects_invalid_calibration_values():
    state = StatsTotalState()

    with pytest.raises(ValueError):
        state.set_offset("source", "nan")

    with pytest.raises(ValueError):
        state.set_desired_value("source", 10.0, None)
