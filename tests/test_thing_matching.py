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
