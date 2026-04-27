from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


COMPONENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "solarwatt_manager"
)


def load_component_module(module_name: str) -> ModuleType:
    module_path = COMPONENT_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"solarwatt_manager_test_{module_name}",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
