from __future__ import annotations

from .module_loader import load_component_module

naming = load_component_module("naming")
clean_item_key = naming.clean_item_key
compose_slug_parts = naming.compose_slug_parts
compose_entity_object_id = naming.compose_entity_object_id
hems_entity_object_id = naming.hems_entity_object_id
hems_item_suffix = naming.hems_item_suffix
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


def test_compose_slug_parts_accepts_slugged_and_display_parts():
    assert compose_slug_parts("kiwigrid_hems", "Today Powerconsumed") == (
        "kiwigrid_hems_today_powerconsumed"
    )


def test_trim_device_tokens_removes_overlapping_device_prefix():
    assert trim_device_tokens("Battery BMS SoC", "Vision Battery") == "bms_soc"


def test_compose_entity_object_id_uses_device_name_without_duplicate_tokens():
    assert compose_entity_object_id("Vision Battery", "Battery BMS SoC") == (
        "vision_battery_bms_soc"
    )


def test_hems_item_suffix_removes_hems_uuid_prefix():
    item_name = (
        "hems_battery_9c319824_bda6_4bbd_ac20_764dc1cfa34c_state_of_charge"
    )

    assert hems_item_suffix(item_name) == "state_of_charge"
    assert item_entity_name(item_name) == "State Of Charge"


def test_hems_entity_object_id_uses_device_hems_property_schema():
    item_name = (
        "hems_battery_9c319824_bda6_4bbd_ac20_764dc1cfa34c_state_of_charge"
    )

    assert hems_entity_object_id(
        "SOLARWATT Battery vision three",
        item_name,
    ) == "solarwatt_battery_vision_three_state_of_charge"


def test_hems_entity_object_id_removes_physical_device_name_repetition():
    item_name = "hems_plug_15922327_c7d9_4fb9_ba65_9073bb627993_requires_override"

    assert hems_entity_object_id(
        "KiwiGrid myStrom (Waschmaschine)",
        item_name,
    ) == "kiwigrid_mystrom_waschmaschine_requires_override"


def test_hems_entity_object_id_trims_repeated_physical_device_tokens_from_suffix():
    item_name = (
        "hems_plug_15922327_c7d9_4fb9_ba65_9073bb627993_"
        "mystrom_waschmaschine_hems_requires_override"
    )

    assert hems_entity_object_id(
        "KiwiGrid myStrom (Waschmaschine)",
        item_name,
    ) == "kiwigrid_mystrom_waschmaschine_requires_override"


def test_hems_entity_object_id_supports_analytics_production_items():
    assert hems_entity_object_id(
        "KiwiGrid HEMS",
        "hems_analytics_production_today_production_powerproduced",
    ) == "kiwigrid_hems_today_production_powerproduced"


def test_analytics_hems_item_name_does_not_duplicate_hems():
    assert item_entity_name(
        "hems_analytics_production_today_production_powerproduced"
    ) == "Today Production Powerproduced"


def test_hems_entity_object_id_supports_analytics_storage_items():
    assert hems_entity_object_id(
        "KiwiGrid HEMS",
        "hems_analytics_storage_today_storage_powerbuffered",
    ) == "kiwigrid_hems_today_storage_powerbuffered"


def test_hems_entity_object_id_supports_analytics_independence_items():
    assert hems_entity_object_id(
        "KiwiGrid HEMS",
        "hems_analytics_independence_today_independence_autarky",
    ) == "kiwigrid_hems_today_independence_autarky"


def test_hems_entity_object_id_supports_analytics_consumption_items():
    assert hems_entity_object_id(
        "KiwiGrid HEMS",
        "hems_analytics_consumption_today_consumption_powerconsumed",
    ) == "kiwigrid_hems_today_consumption_powerconsumed"


def test_hems_entity_object_id_supports_analytics_consumption_month_items():
    assert hems_entity_object_id(
        "KiwiGrid HEMS",
        "hems_analytics_consumption_month_consumption_workconsumed",
    ) == "kiwigrid_hems_month_consumption_workconsumed"


def test_hems_entity_object_id_does_not_duplicate_kiwigrid_stats_device_name():
    assert hems_entity_object_id(
        "KiwiGrid Stats",
        "hems_analytics_consumption_today_consumption_mystrom_wasserpumpe_workin",
    ) == "kiwigrid_stats_today_consumption_mystrom_wasserpumpe_workin"


def test_compose_entity_object_id_uses_only_device_and_sensor_names():
    assert compose_entity_object_id(
        "KiwiGrid Stats",
        "Today Consumption myStrom (Wasserpumpe) WorkIn",
    ) == "kiwigrid_stats_today_consumption_mystrom_wasserpumpe_workin"
