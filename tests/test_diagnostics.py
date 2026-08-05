from __future__ import annotations

from .module_loader import load_component_module_with_stubs, make_module


PACKAGE_NAME = "custom_components.solarwatt_manager"

device_registry = make_module("homeassistant.helpers.device_registry")
entity_registry = make_module("homeassistant.helpers.entity_registry")
homeassistant_helpers = make_module(
    "homeassistant.helpers",
    device_registry=device_registry,
    entity_registry=entity_registry,
)

diagnostics = load_component_module_with_stubs(
    "diagnostics",
    package_name=PACKAGE_NAME,
    stubs={
        "homeassistant": make_module("homeassistant"),
        "homeassistant.core": make_module(
            "homeassistant.core",
            HomeAssistant=object,
        ),
        "homeassistant.helpers": homeassistant_helpers,
        "homeassistant.helpers.device_registry": device_registry,
        "homeassistant.helpers.entity_registry": entity_registry,
        f"{PACKAGE_NAME}.const": make_module(
            f"{PACKAGE_NAME}.const",
            CONF_ENERGY_DELTA_KWH="energy_delta_kwh",
            DEFAULT_ENERGY_DELTA_KWH=0.01,
            DOMAIN="solarwatt_manager",
            SOLARWATTConfigEntry=object,
            get_device_registry_anchor=lambda entry: entry.entry_id,
        ),
    },
)


def test_redact_removes_nested_serial_numbers_only():
    payload = {
        "serialNumber": "ABC-123",
        "nested": {
            "serial": "XYZ-987",
            "serial_number": "DEF-456",
            "model": "Battery flex",
        },
        "label": "Basement battery",
    }

    assert diagnostics._redact(payload) == {
        "nested": {"model": "Battery flex"},
        "label": "Basement battery",
    }


def test_redact_hides_config_connection_and_installation_identifiers():
    assert diagnostics._redact(
        {
            "host": "192.0.2.10",
            "username": "owner@example.com",
            "installation_id": "local:location-uid",
        }
    ) == {
        "host": "REDACTED",
        "username": "REDACTED",
        "installation_id": "REDACTED",
    }


def test_hems_status_payload_exposes_partial_update_state():
    coordinator = type(
        "Coordinator",
        (),
        {
            "hems_last_success": 0.0,
            "hems_last_error": "HEMS endpoint unavailable",
            "hems_cache_age_seconds": 75,
        },
    )()

    assert diagnostics._hems_status_payload(coordinator) == {
        "last_success": "1970-01-01T00:00:00+00:00",
        "last_error": "HEMS endpoint unavailable",
        "cache_age_seconds": 75,
    }
