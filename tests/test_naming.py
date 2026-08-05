from __future__ import annotations

from .module_loader import load_component_module

naming = load_component_module("naming")
clean_item_key = naming.clean_item_key
hems_item_suffix = naming.hems_item_suffix
format_display_name = naming.format_display_name
item_display_name = naming.item_display_name
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
    assert format_display_name("bms soc soh pv ev keba modbus") == (
        "BMS SoC SoH PV EV KEBA Modbus"
    )


def test_item_display_name_normalizes_acronyms_in_provided_labels():
    assert item_display_name(
        "unused",
        "Pv Out / Battery Soc / Ev In",
    ) == "PV Out / Battery SoC / EV In"


def test_item_display_name_preserves_other_label_casing():
    assert item_display_name("unused", "myStrom PV-pump") == "myStrom PV-pump"


def test_slugify_entity_name_removes_unsafe_characters():
    assert slugify_entity_name("Vision Battery: BMS SoC (%)") == (
        "vision_battery_bms_soc"
    )


def test_trim_device_tokens_removes_overlapping_device_prefix():
    assert trim_device_tokens("Battery BMS SoC", "Vision Battery") == "bms_soc"


def test_hems_item_suffix_removes_hems_uuid_prefix():
    item_name = (
        "hems_battery_9c319824_bda6_4bbd_ac20_764dc1cfa34c_state_of_charge"
    )

    assert hems_item_suffix(item_name) == "state_of_charge"
    assert item_entity_name(item_name) == "State Of Charge"


def test_smart_heater_item_name_removes_hems_uuid_prefix():
    item_name = (
        "hems_smart_heater_700ff539_7ae2_4802_83f8_afa1949ec7d0_temperature"
    )

    assert hems_item_suffix(item_name) == "temperature"
    assert item_entity_name(item_name) == "Temperature"


def test_analytics_hems_item_name_does_not_duplicate_hems():
    assert item_entity_name(
        "hems_analytics_production_today_production_powerproduced"
    ) == "Today Production Powerproduced"


def test_entity_suggested_object_id_uses_sensor_name_without_device_prefix():
    assert slugify_entity_name(
        trim_device_tokens("Month Finance saving", "KiwiGrid Stats")
    ) == "month_finance_saving"
