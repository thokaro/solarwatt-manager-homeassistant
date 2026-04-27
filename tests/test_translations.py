from __future__ import annotations

import json
from pathlib import Path


TRANSLATIONS_DIR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "solarwatt_manager"
    / "translations"
)


def _flatten_keys(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return {prefix}

    keys: set[str] = set()
    for child_key, child_value in value.items():
        child_prefix = f"{prefix}.{child_key}" if prefix else str(child_key)
        keys.update(_flatten_keys(child_value, child_prefix))
    return keys


def test_translation_files_are_valid_json():
    for path in TRANSLATIONS_DIR.glob("*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))


def test_translations_keep_same_key_structure_as_english():
    english = json.loads((TRANSLATIONS_DIR / "en.json").read_text(encoding="utf-8"))
    expected_keys = _flatten_keys(english)

    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        translated = json.loads(path.read_text(encoding="utf-8"))

        assert _flatten_keys(translated) == expected_keys, path.name
