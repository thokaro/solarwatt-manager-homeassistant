from __future__ import annotations

import json
import re
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


def test_connection_forms_separate_local_online_and_general_sections():
    expected_connection_sections = {"local_connection", "kiwigrid_connection"}

    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        translated = json.loads(path.read_text(encoding="utf-8"))
        config_steps = translated["config"]["step"]
        options_sections = translated["options"]["step"]["init"]["sections"]

        assert set(config_steps["user"]["sections"]) == {
            *expected_connection_sections,
            "general_settings",
        }
        assert set(config_steps["reauth_confirm"]["sections"]) == (
            expected_connection_sections
        )
        assert set(config_steps["reconfigure"]["sections"]) == (
            expected_connection_sections
        )
        assert set(options_sections) == {
            "device_selection",
            *expected_connection_sections,
            "general_settings",
        }
        for sections in (config_steps["user"]["sections"], options_sections):
            assert "scan_interval" in sections["local_connection"]["data"]
            assert set(sections["general_settings"]["data"]) == {
                "energy_delta_kwh", "power_unavailable_threshold",
            }
            assert {
                "kiwigrid_hems_scan_interval",
                "kiwigrid_flow_scan_interval",
                "kiwigrid_stats_scan_interval",
                "kiwigrid_profile_cache_interval",
            } <= sections["kiwigrid_connection"]["data"].keys()


def test_connection_descriptions_use_plain_text_urls() -> None:
    """Section descriptions display plain text, so Markdown links stay visible."""
    expected_urls = {
        "local_connection": "http://energymanager.local/",
        "kiwigrid_connection": "https://new.energymanager.com/",
    }

    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        translated = json.loads(path.read_text(encoding="utf-8"))
        forms = (
            translated["config"]["step"]["user"],
            translated["config"]["step"]["reauth_confirm"],
            translated["config"]["step"]["reconfigure"],
            translated["options"]["step"]["init"],
        )
        for form in forms:
            for section, url in expected_urls.items():
                description = form["sections"][section]["description"]
                assert url in description, (path.name, section)
                assert not re.search(r"\[[^\]]*\]\([^)]*\)", description), (
                    path.name,
                    section,
                )


def test_section_descriptions_do_not_rely_on_line_breaks() -> None:
    """Section descriptions collapse whitespace in the frontend."""
    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        translated = json.loads(path.read_text(encoding="utf-8"))
        for flow in ("config", "options"):
            for step in translated[flow]["step"].values():
                for name, section in step.get("sections", {}).items():
                    description = section.get("description", "")
                    assert "\n" not in description, (path.name, name)
