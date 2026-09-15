from __future__ import annotations

from types import SimpleNamespace

import pytest
import voluptuous as vol

from .module_loader import (
    load_component_module_with_stubs,
    make_homeassistant_stubs,
    make_module,
)


class _ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()


class _OptionsFlow:
    @property
    def config_entry(self):
        return self._config_entry


PACKAGE_NAME = "solarwatt_manager_options_test"
stubs = make_homeassistant_stubs()
stubs["homeassistant.config_entries"].ConfigFlow = _ConfigFlow
stubs["homeassistant.config_entries"].OptionsFlow = _OptionsFlow
stubs.update({
    "homeassistant.data_entry_flow": make_module(
        "homeassistant.data_entry_flow", section=lambda schema, options: schema,
    ),
    f"{PACKAGE_NAME}.client": make_module(
        f"{PACKAGE_NAME}.client",
        SOLARWATTClient=object,
        SolarwattAuthError=type("AuthError", (Exception,), {}),
        SolarwattConnectionError=type("ConnectionError", (Exception,), {}),
        SolarwattNotManagerError=type("NotManagerError", (Exception,), {}),
        SolarwattProtocolError=type("ProtocolError", (Exception,), {}),
    ),
    f"{PACKAGE_NAME}.entity_helpers": make_module(
        f"{PACKAGE_NAME}.entity_helpers", sync_selected_thing_entities=lambda *args: None,
    ),
})
config_flow = load_component_module_with_stubs(
    "config_flow", package_name=PACKAGE_NAME, stubs=stubs,
)


@pytest.mark.parametrize("scan,hems", [(15, 120), (30, 90), (60, 600)])
def test_options_form_preserves_existing_poll_intervals(scan, hems):
    current = {"scan_interval": scan, "kiwigrid_hems_scan_interval": hems}
    schema = vol.Schema(config_flow._build_option_schema_fields(current))
    submitted = schema({})
    flow = config_flow.SOLARWATTItemsOptionsFlow(SimpleNamespace(options=current))
    saved = flow._build_options_data(submitted)

    assert saved["kiwigrid_flow_scan_interval"] == scan
    assert saved["kiwigrid_stats_scan_interval"] == hems
    assert saved["kiwigrid_profile_cache_interval"] == 3600
    assert not config_flow._validate_options_data(saved)


def test_options_without_new_fields_preserve_legacy_values():
    current = {"scan_interval": 30, "kiwigrid_hems_scan_interval": 90}
    saved = config_flow._normalize_options_input({}, current)

    assert saved["kiwigrid_flow_scan_interval"] == 30
    assert saved["kiwigrid_stats_scan_interval"] == 90


def test_options_save_independent_intervals_and_preserve_selection():
    current = {
        "scan_interval": 15,
        "kiwigrid_hems_scan_interval": 120,
        "enabled_things": ["existing-device"],
    }
    flow = config_flow.SOLARWATTItemsOptionsFlow(SimpleNamespace(options=current))
    saved = flow._build_options_data({
        "kiwigrid_connection": {
            "kiwigrid_flow_scan_interval": "30",
            "kiwigrid_stats_scan_interval": "300",
            "kiwigrid_profile_cache_interval": "1800",
        },
    })

    assert saved["scan_interval"] == 15
    assert saved["kiwigrid_hems_scan_interval"] == 120
    assert saved["kiwigrid_flow_scan_interval"] == 30
    assert saved["kiwigrid_stats_scan_interval"] == 300
    assert saved["kiwigrid_profile_cache_interval"] == 1800
    assert saved["enabled_things"] == ["existing-device"]
    assert not config_flow._validate_options_data(saved)


@pytest.mark.parametrize("key", [
    "kiwigrid_flow_scan_interval",
    "kiwigrid_stats_scan_interval",
    "kiwigrid_profile_cache_interval",
])
@pytest.mark.parametrize("value", [9, 3601, "invalid"])
def test_options_reject_invalid_cloud_intervals(key, value):
    saved = config_flow._normalize_options_input({key: value})
    assert config_flow._validate_options_data(saved) == {key: "invalid_scan_interval"}


def test_setup_and_options_forms_expose_the_same_cloud_intervals():
    keys = {
        "kiwigrid_hems_scan_interval",
        "kiwigrid_flow_scan_interval",
        "kiwigrid_stats_scan_interval",
        "kiwigrid_profile_cache_interval",
    }
    flow = config_flow.SOLARWATTItemsConfigFlow()
    form = flow._build_user_schema()({
        "local_connection": {},
        "kiwigrid_connection": {},
        "general_settings": {},
    })
    _, options = config_flow._normalize_user_input(form)

    assert keys <= form["kiwigrid_connection"].keys()
    assert options["kiwigrid_flow_scan_interval"] == options["scan_interval"]
    assert options["kiwigrid_stats_scan_interval"] == options["kiwigrid_hems_scan_interval"]
    assert options["kiwigrid_profile_cache_interval"] == 3600


@pytest.mark.parametrize("step", ["setup", "options"])
def test_poll_intervals_are_saved_from_their_connection_sections(step, monkeypatch):
    current = {"scan_interval": 15, "kiwigrid_hems_scan_interval": 30}
    if step == "setup":
        flow = config_flow.SOLARWATTItemsConfigFlow()
        schema = flow._build_user_schema()
    else:
        flow = config_flow.SOLARWATTItemsOptionsFlow(
            SimpleNamespace(data={}, options=current)
        )
        monkeypatch.setattr(flow, "_available_things", lambda values: [])
        schema = flow._build_options_schema()

    submitted = {
        "local_connection": {"scan_interval": "45"},
        "kiwigrid_connection": {
            "kiwigrid_flow_scan_interval": "30",
            "kiwigrid_stats_scan_interval": "300",
            "kiwigrid_profile_cache_interval": "3600",
        },
        "general_settings": {"energy_delta_kwh": "0.02"},
    }
    if step == "options":
        submitted["device_selection"] = {}
    form = schema(submitted)
    saved = config_flow._normalize_options_input(form, current)

    assert "scan_interval" not in form["general_settings"]
    assert form["local_connection"]["scan_interval"] == 45
    assert saved["scan_interval"] == 45
    assert saved["kiwigrid_flow_scan_interval"] == 30
    assert saved["kiwigrid_stats_scan_interval"] == 300
    assert saved["kiwigrid_profile_cache_interval"] == 3600
    assert saved["energy_delta_kwh"] == 0.02
    assert not config_flow._validate_options_data(saved)
