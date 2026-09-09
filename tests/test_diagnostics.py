from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from .module_loader import load_component_module_with_stubs, make_homeassistant_stubs


diagnostics = load_component_module_with_stubs(
    "diagnostics",
    package_name="solarwatt_manager_diagnostics_test",
    stubs=make_homeassistant_stubs(),
)


def test_redact_removes_serial_numbers_and_hides_device_labels():
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
        "label": "REDACTED",
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
            "hems_partial_errors": ("analytics year timeout",),
            "hems_cache_age_seconds": 75,
        },
    )()

    assert diagnostics._hems_status_payload(coordinator) == {
        "last_success": "1970-01-01T00:00:00+00:00",
        "last_error": "HEMS endpoint unavailable",
        "partial_errors": ["analytics year timeout"],
        "cache_age_seconds": 75,
    }


@pytest.mark.parametrize("key", [
    "kiwigrid_hems_username", "userName", "access-token", "api.key", "deviceID",
    "bridge_uid", "device_uuid", "identifier", "mac", "ip_address", "email",
    "location", "latitude", "longitude", "gps", "coordinates", "device_name",
    "friendlyName", "generatedLabel", "description", "last_exception",
])
def test_redact_sensitive_field_variants_without_mutating_input(key):
    payload = {"nested": [{key: {"value": "private"}, "power": 123.5}]}
    original = deepcopy(payload)

    assert diagnostics._redact(payload) == {
        "nested": [{key: "REDACTED", "power": 123.5}]
    }
    assert payload == original


@pytest.mark.parametrize("value", [
    "owner@example.com", "192.0.2.10", "2001:db8::1", "fe80::1234%eth0",
    "00:11:22:33:44:55", "AA-BB-CC-DD-EE-FF",
    "12345678-1234-1234-1234-123456789abc", "https://manager.local/?token=private",
])
def test_redact_identifiers_in_text_and_dictionary_keys(value):
    assert diagnostics._redact({"metadata": f"before {value} after"}) == {
        "metadata": "before REDACTED after"
    }
    assert value not in json.dumps(diagnostics._redact({value: [value]}))
    assert value not in json.dumps(diagnostics._redact({f"sensor_{value}": f"sensor_{value}"}))


def test_full_export_hides_private_data_and_preserves_measurements():
    uid = "12345678-1234-1234-1234-123456789abc"
    power_item = SimpleNamespace(
        oh_type="Number:Power", label="Private room", category="energy_overview",
        raw={"state": "123.5 W"}, parsed=SimpleNamespace(value=123.5, unit="W"),
    )
    string_item = SimpleNamespace(
        oh_type="String", label="Owner name", raw={"state": "123456789"},
        parsed=SimpleNamespace(value="123456789"),
    )
    coordinator = SimpleNamespace(
        data={f"power_{uid}": power_item, "opaque-item": string_item},
        things={
            uid: {"label": "Private room", "bridgeUID": "private-bridge",
                  "thingTypeUID": "battery:standard", "channels": [{}],
                  "statusInfo": {"status": "ONLINE", "statusDetail": "private-detail"},
                  "properties": {"serialNumber": "SERIAL-PRIVATE", "mac": "001122334455", "latitude": 52.12345}},
            "opaque-private-uid": {"label": "Private garage"},
        },
        last_exception=ValueError("unlisted-password"),
        hems_last_error="private-host.local rejected unlisted-password",
        hems_partial_errors=("private-endpoint failed",),
    )
    entry = SimpleNamespace(
        entry_id="private-entry", title="SOLARWATT (private-host.local)",
        domain="solarwatt_manager", runtime_data=coordinator,
        data={"host": "private-host.local", "password": "local-secret"},
        options={"kiwigrid_hems_username": "owner@example.com", "enabled_things": [uid]},
    )
    device = SimpleNamespace(name="Private garage", manufacturer="SOLARWATT", model="Manager", sw_version="1.2.3", hw_version=None)
    state = SimpleNamespace(
        name="Private room", attributes={"device_class": "energy", "unit_of_measurement": "kWh"},
        last_updated=None, last_changed=None,
    )
    hass = SimpleNamespace(
        devices=SimpleNamespace(async_get_device_by_identifier=lambda *args: device),
        entities=SimpleNamespace(entries=[SimpleNamespace(entity_id="sensor.private_house")]),
        states=SimpleNamespace(get=lambda entity_id: state),
    )
    original = deepcopy((entry.data, entry.options, coordinator.data, coordinator.things))

    result = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))
    serialized = json.dumps(result)
    for secret in (
        uid, "private", "Private", "SERIAL-PRIVATE", "001122334455", "52.12345",
        "owner@example.com", "local-secret", "unlisted-password", "123456789",
    ):
        assert secret not in serialized
    assert set(result["things"]["things_compact"]) == {"thing_1", "thing_2"}
    assert result["things"]["things_compact"]["thing_1"]["status"] == "ONLINE"
    assert result["things"]["things_compact"]["thing_1"]["thing_type_uid"] == "battery:standard"
    assert result["device"]["model"] == "Manager"
    assert result["device"]["sw_version"] == "1.2.3"
    assert result["coordinator"]["numeric_items"] == 1
    assert result["data_items_compact"]["item_1"]["parsed_value"] == 123.5
    assert result["data_items_compact"]["item_1"]["raw_state"] == "123.5 W"
    assert result["data_items_compact"]["item_1"]["unit"] == "W"
    assert result["data_items_compact"]["item_2"]["raw_state"] == "REDACTED"
    assert result["data_items_compact"]["item_2"]["parsed_value"] == "REDACTED"
    assert result["problem_items"]["problem_items_top_20"] == [{"item": "item_2", "issue": "non-numeric value"}]
    assert set(result["energy_settings"]["energy_sensors_last_write"]) == {"entity_1"}
    assert (entry.data, entry.options, coordinator.data, coordinator.things) == original
