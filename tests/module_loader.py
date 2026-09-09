from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Mapping


COMPONENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "solarwatt_manager"
)


def load_component_module(module_name: str) -> ModuleType:
    """Load one component module without importing the Home Assistant package."""
    return _load_module(
        f"solarwatt_manager_test_{module_name}",
        COMPONENT_DIR / f"{module_name}.py",
    )


def make_module(name: str, **attributes: Any) -> ModuleType:
    """Create a lightweight module stub with the supplied attributes."""
    module = ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


class _ConfigEntryStub:
    @classmethod
    def __class_getitem__(cls, item: Any) -> type:
        return cls


def make_homeassistant_stubs() -> dict[str, ModuleType]:
    """Build shared HA imports; registry instances come from the test's hass object."""
    dr = make_module(
        "homeassistant.helpers.device_registry", DeviceInfo=dict,
        async_get=lambda hass: hass.devices,
    )
    er = make_module(
        "homeassistant.helpers.entity_registry",
        async_get=lambda hass: hass.entities,
        async_entries_for_config_entry=lambda registry, entry_id: registry.entries,
    )
    return {
        "homeassistant": make_module("homeassistant"),
        "homeassistant.config_entries": make_module(
            "homeassistant.config_entries", ConfigEntry=_ConfigEntryStub
        ),
        "homeassistant.core": make_module(
            "homeassistant.core", HomeAssistant=object, callback=lambda func: func
        ),
        "homeassistant.helpers": make_module(
            "homeassistant.helpers", device_registry=dr, entity_registry=er
        ),
        "homeassistant.helpers.device_registry": dr,
        "homeassistant.helpers.entity_registry": er,
    }


def load_component_module_with_stubs(
    module_name: str,
    *,
    package_name: str,
    stubs: Mapping[str, ModuleType],
) -> ModuleType:
    """Load a component module with temporary dependency modules."""
    package = stubs.get(package_name) or make_module(package_name)
    package.__path__ = [str(COMPONENT_DIR)]
    temporary_modules = {
        package_name: package,
        **stubs,
    }
    qualified_name = f"{package_name}.{module_name}"
    previous_modules = {
        name: sys.modules.get(name)
        for name in (*temporary_modules, qualified_name)
    }
    sys.modules.update(temporary_modules)

    try:
        return _load_module(
            qualified_name,
            COMPONENT_DIR / f"{module_name}.py",
        )
    finally:
        for name, previous_module in previous_modules.items():
            if previous_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module


def _load_module(module_name: str, module_path: Path) -> ModuleType:
    """Execute and return one module from a filesystem path."""
    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
