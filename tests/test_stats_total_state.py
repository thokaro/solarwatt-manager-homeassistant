from __future__ import annotations

import pytest

from .module_loader import load_component_module

stats_total_state = load_component_module("stats_total_state")
StatsTotalState = stats_total_state.StatsTotalState


def test_stats_total_state_adds_previous_year_when_year_value_resets():
    state = StatsTotalState()

    assert state.value_with_offset("source", 100.0) == 100.0
    assert state.value_with_offset("source", 150.0) == 150.0
    assert state.value_with_offset("source", 0.0) == 150.0
    assert state.value_with_offset("source", 25.0) == 175.0


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
