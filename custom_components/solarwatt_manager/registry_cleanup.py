from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SOLARWATTConfigEntry, build_thing_device_identifier

_LOGGER = logging.getLogger(__name__)


def cleanup_empty_channel_thing_diagnostics(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    things: Mapping[str, Any] | None,
) -> None:
    """Remove thing diagnostics entities/devices for things without channels."""
    ent_reg = er.async_get(hass)
    empty_channel_thing_uids = {
        str(thing.get("UID") or thing.get("uid") or thing_uid).strip()
        for thing_uid, thing in (things or {}).items()
        if not isinstance(thing.get("channels"), list) or not thing.get("channels")
    }
    if not empty_channel_thing_uids:
        return
    unique_ids_to_remove = {
        unique_id
        for thing_uid in empty_channel_thing_uids
        for unique_id in (
            f"{entry.entry_id}_thing_{thing_uid}",
            f"{entry.entry_id}_thing_{thing_uid}_diagnostics_refresh",
        )
    }

    removed = 0
    for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if registry_entry.platform != DOMAIN or not registry_entry.unique_id:
            continue
        if registry_entry.unique_id not in unique_ids_to_remove:
            continue
        ent_reg.async_remove(registry_entry.entity_id)
        removed += 1

    if removed:
        _LOGGER.info(
            "Removed %s SOLARWATT thing diagnostics entities without channels for entry %s",
            removed,
            entry.entry_id,
        )

    _remove_orphaned_thing_devices(hass, entry, empty_channel_thing_uids)


def _remove_orphaned_thing_devices(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    thing_uids: set[str],
) -> None:
    """Detach the config entry from empty-channel thing devices if they no longer have entities."""
    host = str(entry.data.get("host") or "").strip().lower()
    if not host or not thing_uids:
        return

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)

    for thing_uid in thing_uids:
        device = dev_reg.async_get_device(
            identifiers={build_thing_device_identifier(host, thing_uid)}
        )
        if not device or entry.entry_id not in device.config_entries:
            continue
        if any(
            registry_entry.device_id == device.id
            for registry_entry in registry_entries
            if registry_entry.platform == DOMAIN
        ):
            continue
        dev_reg.async_update_device(
            device_id=device.id,
            remove_config_entry_id=entry.entry_id,
        )
