from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def _load_diagnostics_module():
    package_name = "custom_components.solarwatt_manager"
    component_dir = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "solarwatt_manager"
    )

    homeassistant = ModuleType("homeassistant")
    homeassistant_core = ModuleType("homeassistant.core")
    homeassistant_core.HomeAssistant = object
    homeassistant_helpers = ModuleType("homeassistant.helpers")
    device_registry = ModuleType("homeassistant.helpers.device_registry")
    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    homeassistant_helpers.device_registry = device_registry
    homeassistant_helpers.entity_registry = entity_registry

    package = ModuleType(package_name)
    package.__path__ = [str(component_dir)]
    const = ModuleType(f"{package_name}.const")
    const.CONF_ENERGY_DELTA_KWH = "energy_delta_kwh"
    const.DEFAULT_ENERGY_DELTA_KWH = 0.01
    const.DOMAIN = "solarwatt_manager"
    const.SOLARWATTConfigEntry = object

    stubs = {
        "homeassistant": homeassistant,
        "homeassistant.core": homeassistant_core,
        "homeassistant.helpers": homeassistant_helpers,
        "homeassistant.helpers.device_registry": device_registry,
        "homeassistant.helpers.entity_registry": entity_registry,
        package_name: package,
        f"{package_name}.const": const,
    }
    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)

    module_name = f"{package_name}.diagnostics"
    spec = importlib.util.spec_from_file_location(module_name, component_dir / "diagnostics.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)
        for name, previous_module in previous.items():
            if previous_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module


diagnostics = _load_diagnostics_module()


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
