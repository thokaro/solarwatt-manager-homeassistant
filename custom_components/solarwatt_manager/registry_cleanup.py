from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SOLARWATTConfigEntry
from .entity_helpers import detach_entityless_thing_devices
from .hems_api import is_hems_thing

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
        if not is_hems_thing(thing)
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

    detach_entityless_thing_devices(hass, entry, empty_channel_thing_uids)
