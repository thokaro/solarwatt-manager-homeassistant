from __future__ import annotations

import pytest

from .module_loader import load_component_module

state_parser = load_component_module("state_parser")
parse_state = state_parser.parse_state


@pytest.mark.parametrize("raw_state", [None, "NULL", "UNDEF", "UNINITIALIZED"])
def test_parse_unavailable_states(raw_state):
    parsed = parse_state(raw_state)

    assert parsed.value is None
    assert parsed.unit is None


@pytest.mark.parametrize(
    ("raw_state", "expected_value", "expected_unit"),
    [
        ("123 Wh", 0.123, "kWh"),
        ("3600 Ws", 0.001, "kWh"),
        ("1500 mA", 1.5, "A"),
        ("230 V", 230, "V"),
        ("12 Ohm", 12, "\u03a9"),
    ],
)
def test_parse_numeric_states_with_normalized_units(
    raw_state,
    expected_value,
    expected_unit,
):
    parsed = parse_state(raw_state)

    assert parsed.value == expected_value
    assert parsed.unit == expected_unit


def test_parse_timestamped_state():
    parsed = parse_state("1714131600000|1234 W")

    assert parsed.timestamp_ms == 1714131600000
    assert parsed.value == 1234
    assert parsed.unit == "W"


def test_parse_unit_from_state_description_pattern():
    parsed = parse_state("24.5", "%.1f \\u00b0C", "Number:Temperature")

    assert parsed.value == 24.5
    assert parsed.unit == "\u00b0C"


def test_parse_switch_on_off_as_boolean():
    assert parse_state("ON", oh_type="Switch").value is True
    assert parse_state("OFF", oh_type="Switch").value is False


def test_parse_string_on_off_as_text():
    assert parse_state("ON", oh_type="String").value == "ON"
    assert parse_state("OFF", oh_type="String").value == "OFF"
