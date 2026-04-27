from __future__ import annotations

from .module_loader import load_component_module

naming = load_component_module("naming")
clean_item_key = naming.clean_item_key
compose_entity_object_id = naming.compose_entity_object_id
format_display_name = naming.format_display_name
item_entity_name = naming.item_entity_name
normalize_item_name = naming.normalize_item_name
slugify_entity_name = naming.slugify_entity_name
trim_device_tokens = naming.trim_device_tokens


def test_clean_item_key_strips_openhab_metadata_prefix():
    assert clean_item_key("#foo_bar") == "foo_bar"


def test_normalize_item_name_strips_installation_specific_prefix():
    raw = "pvplant_standard_abc123_harmonized_pv_power"

    assert normalize_item_name(raw) == "harmonized_pv_power"


def test_item_entity_name_formats_channel_name():
    raw = "pvplant_standard_abc123_harmonized_bms_soc"

    assert item_entity_name(raw) == "BMS SoC"


def test_format_display_name_preserves_known_acronyms():
    assert format_display_name("bms soc soh pv keba modbus") == (
        "BMS SoC SoH PV KEBA Modbus"
    )


def test_slugify_entity_name_removes_unsafe_characters():
    assert slugify_entity_name("Vision Battery: BMS SoC (%)") == (
        "vision_battery_bms_soc"
    )


def test_trim_device_tokens_removes_overlapping_device_prefix():
    assert trim_device_tokens("Battery BMS SoC", "Vision Battery") == "bms_soc"


def test_compose_entity_object_id_uses_device_name_without_duplicate_tokens():
    assert compose_entity_object_id("Vision Battery", "Battery BMS SoC") == (
        "vision_battery_bms_soc"
    )
