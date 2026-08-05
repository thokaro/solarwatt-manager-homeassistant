from __future__ import annotations

from .module_loader import load_component_module


thing_matching = load_component_module("thing_matching")


def test_resolve_thing_uid_prefers_matching_serial_number():
    existing = {
        "local:battery": {
            "label": "Battery flex",
            "properties": {"serialNumber": "BAT-123", "model": "Battery flex"},
        }
    }
    incoming = {
        "label": "Cloud battery",
        "properties": {"serial_number": "ignored", "serial": "BAT-123"},
    }

    assert thing_matching.resolve_thing_uid(existing, incoming, "cloud-uuid") == "local:battery"


def test_resolve_thing_uid_does_not_merge_different_serial_numbers():
    existing = {
        "local:battery": {
            "label": "Battery flex",
            "properties": {"serialNumber": "BAT-123"},
        }
    }
    incoming = {
        "label": "Battery flex",
        "properties": {"serialNumber": "BAT-456"},
    }

    assert thing_matching.resolve_thing_uid(existing, incoming, "cloud-uuid") == "cloud-uuid"


def test_merge_selection_things_preserves_local_label_and_merges_metadata():
    existing = {
        "local:battery": {
            "UID": "local:battery",
            "label": "Battery flex",
            "properties": {"serialNumber": "BAT-123"},
            "channels": [{"uid": "local-power"}],
        }
    }
    incoming = {
        "cloud-uuid": {
            "UID": "cloud-uuid",
            "label": "Cloud battery",
            "properties": {"serialNumber": "BAT-123", "model": "Battery flex"},
            "channels": [{"uid": "cloud-power"}],
        }
    }

    merged = thing_matching.merge_selection_things(existing, incoming)

    assert set(merged) == {"local:battery"}
    assert merged["local:battery"]["label"] == "Battery flex"
    assert merged["local:battery"]["properties"]["model"] == "Battery flex"
    assert [channel["uid"] for channel in merged["local:battery"]["channels"]] == [
        "local-power",
        "cloud-power",
    ]


def test_merge_selection_things_matches_local_keba_and_cloud_device():
    existing = {
        "keba:wallbox:25948592": {
            "UID": "keba:wallbox:25948592",
            "label": "Keba P30 PV-Edition",
            "thingTypeUID": "keba:wallbox",
            "properties": {
                "solarwatt.hemsConfigurator": "true",
                "thingTypeTitle": "KEBA KeContact P30",
            },
            "channels": [],
        }
    }
    incoming = {
        "cloud-keba": {
            "UID": "cloud-keba",
            "label": "Keba P30 PV-Edition",
            "thingTypeUID": "kiwigrid-hems:evstation",
            "properties": {
                "kiwigridKind": "evstation",
                "model": "KC-P30-EC2204U2-E00-PV",
            },
            "channels": [],
        }
    }

    merged = thing_matching.merge_selection_things(existing, incoming)

    assert set(merged) == {"keba:wallbox:25948592"}
    properties = merged["keba:wallbox:25948592"]["properties"]
    assert properties["kiwigridKind"] == "evstation"
    assert properties["model"] == "KC-P30-EC2204U2-E00-PV"


def test_merge_selection_things_keeps_distinct_mystrom_devices():
    existing = {
        "mystrom:switch:C8F09E96C640": {
            "UID": "mystrom:switch:C8F09E96C640",
            "label": "myStrom (Waschmaschine)",
            "thingTypeUID": "mystrom:switch",
            "properties": {
                "solarwatt.hemsConfigurator": "true",
                "thingTypeTitle": "myStrom WiFi Switch",
            },
            "channels": [],
        },
        "mystrom:switch:083A8D969CF8": {
            "UID": "mystrom:switch:083A8D969CF8",
            "label": "myStrom (Wasserpumpe)",
            "thingTypeUID": "mystrom:switch",
            "properties": {
                "solarwatt.hemsConfigurator": "true",
                "thingTypeTitle": "myStrom WiFi Switch",
            },
            "channels": [],
        },
    }
    incoming = {
        "cloud-washing-machine": {
            "UID": "cloud-washing-machine",
            "label": "myStrom (Waschmaschine)",
            "thingTypeUID": "kiwigrid-hems:plug",
            "properties": {"kiwigridKind": "plug", "model": "PLUG"},
            "channels": [],
        },
        "cloud-water-pump": {
            "UID": "cloud-water-pump",
            "label": "myStrom (Wasserpumpe)",
            "thingTypeUID": "kiwigrid-hems:plug",
            "properties": {"kiwigridKind": "plug", "model": "PLUG"},
            "channels": [],
        },
    }

    merged = thing_matching.merge_selection_things(existing, incoming)

    assert set(merged) == {
        "mystrom:switch:C8F09E96C640",
        "mystrom:switch:083A8D969CF8",
    }
    assert all(
        thing["properties"]["kiwigridKind"] == "plug"
        for thing in merged.values()
    )


def test_merge_thing_records_uses_cloud_status_for_offline_local_device():
    existing = {
        "UID": "local:battery",
        "label": "local:battery",
        "statusInfo": {"status": "OFFLINE"},
    }
    incoming = {
        "label": "Battery flex",
        "statusInfo": {"status": "ONLINE", "statusDetail": "NONE"},
    }

    merged = thing_matching.merge_thing_records(existing, incoming)

    assert merged["label"] == "Battery flex"
    assert merged["statusInfo"] == {"status": "ONLINE", "statusDetail": "NONE"}
