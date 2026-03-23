from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    SOLARWATTConfigEntry,
    build_thing_device_identifier,
)
from .entity_helpers import build_item_sensor_unique_id
from .naming import normalized_item_name_variants

_LOGGER = logging.getLogger(__name__)


def migrate_item_sensor_unique_ids(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
) -> None:
    """Migrate legacy normalized item unique_ids to raw item-name unique_ids."""
    migration_map: dict[str, str] = {}
    for item_name in _item_sensor_names(items):
        new_unique_id = build_item_sensor_unique_id(entry.entry_id, item_name)
        legacy_unique_ids = {
            f"{entry.entry_id}_{normalized_name}"
            for normalized_name in normalized_item_name_variants(item_name or "")
        }
        for old_unique_id in legacy_unique_ids:
            if old_unique_id != new_unique_id:
                migration_map[old_unique_id] = new_unique_id

    if not migration_map:
        return

    ent_reg, entries = _item_sensor_entries(hass, entry)
    used_unique_ids = {registry_entry.unique_id for registry_entry in entries}

    migrated = 0
    skipped = 0
    for registry_entry in entries:
        target_unique_id = migration_map.get(registry_entry.unique_id)
        if not target_unique_id:
            continue
        if (
            target_unique_id in used_unique_ids
            and target_unique_id != registry_entry.unique_id
        ):
            skipped += 1
            _LOGGER.warning(
                "Skipping unique_id migration for %s due to collision: %s",
                registry_entry.entity_id,
                target_unique_id,
            )
            continue

        ent_reg.async_update_entity(
            registry_entry.entity_id,
            new_unique_id=target_unique_id,
        )
        used_unique_ids.discard(registry_entry.unique_id)
        used_unique_ids.add(target_unique_id)
        migrated += 1

    if migrated or skipped:
        _LOGGER.info(
            "Unique ID migration finished for entry %s: migrated=%s skipped=%s",
            entry.entry_id,
            migrated,
            skipped,
        )


def cleanup_legacy_device_registry_entries(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
) -> None:
    """Remove obsolete registry entries left behind by older releases."""
    ent_reg = er.async_get(hass)
    legacy_unique_ids = {f"{entry.entry_id}_diagnostics_refresh"}
    removed = 0

    for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if registry_entry.platform != DOMAIN or not registry_entry.unique_id:
            continue
        if registry_entry.unique_id not in legacy_unique_ids:
            continue
        ent_reg.async_remove(registry_entry.entity_id)
        removed += 1

    if removed:
        _LOGGER.info(
            "Removed %s obsolete SOLARWATT registry entries for entry %s",
            removed,
            entry.entry_id,
        )

    _remove_orphaned_root_device(hass, entry)


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


def migrate_item_entities_to_thing_devices(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None,
) -> None:
    """Move existing item entities from the legacy root device to their thing device."""
    host = str(entry.data.get("host") or "").strip().lower()
    if not host:
        return

    ent_reg, entries = _item_sensor_entries(hass, entry)
    entries_by_unique_id = {
        registry_entry.unique_id: registry_entry
        for registry_entry in entries
        if registry_entry.unique_id
    }
    if not entries_by_unique_id:
        return

    dev_reg = dr.async_get(hass)
    moved = 0
    for item_name in _item_sensor_names(items):
        thing_uid = (item_to_thing_uid or {}).get(item_name)
        if not thing_uid:
            continue

        registry_entry = entries_by_unique_id.get(
            build_item_sensor_unique_id(entry.entry_id, item_name)
        )
        if not registry_entry:
            continue

        target_device = dev_reg.async_get_device(
            identifiers={build_thing_device_identifier(host, thing_uid)}
        )
        if not target_device or registry_entry.device_id == target_device.id:
            continue

        if not _update_entity_device(ent_reg, registry_entry.entity_id, target_device.id):
            continue
        moved += 1

    if moved:
        _LOGGER.info(
            "Moved %s SOLARWATT item entities from legacy root device to thing devices for entry %s",
            moved,
            entry.entry_id,
        )


def _remove_orphaned_root_device(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
) -> None:
    """Detach the config entry from the legacy root device if it no longer has entities."""
    host = str(entry.data.get("host") or "").strip().lower()
    if not host:
        return

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, host)})
    if not device or entry.entry_id not in device.config_entries:
        return

    ent_reg = er.async_get(hass)
    if any(
        registry_entry.device_id == device.id
        for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if registry_entry.platform == DOMAIN
    ):
        return

    dev_reg.async_update_device(
        device_id=device.id,
        remove_config_entry_id=entry.entry_id,
    )


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


def _update_entity_device(
    ent_reg: er.EntityRegistry,
    entity_id: str,
    target_device_id: str,
) -> bool:
    """Update a registry entry to point at a different device if supported."""
    try:
        parameters = inspect.signature(ent_reg.async_update_entity).parameters
    except (TypeError, ValueError):
        parameters = {}

    if "device_id" in parameters:
        ent_reg.async_update_entity(entity_id, device_id=target_device_id)
        return True
    if "new_device_id" in parameters:
        ent_reg.async_update_entity(entity_id, new_device_id=target_device_id)
        return True

    _LOGGER.debug("Entity registry does not support device migration for %s", entity_id)
    return False


def _item_sensor_entries(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry
) -> tuple[er.EntityRegistry, list[er.RegistryEntry]]:
    """Return sensor registry entries for this config entry excluding thing diagnostics."""
    ent_reg = er.async_get(hass)
    item_prefix = f"{entry.entry_id}_"
    thing_prefix = f"{entry.entry_id}_thing_"
    entries = [
        registry_entry
        for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if registry_entry.domain == "sensor"
        and registry_entry.platform == DOMAIN
        and registry_entry.unique_id
        and registry_entry.unique_id.startswith(item_prefix)
        and not registry_entry.unique_id.startswith(thing_prefix)
    ]
    return ent_reg, entries


def _item_sensor_names(items: Mapping[str, Any] | None) -> list[str]:
    """Return coordinator item names that should be exposed as sensors."""
    return [
        item_name
        for item_name, item in (items or {}).items()
        if not _is_switch_item(item)
    ]


def _is_switch_item(item: Any) -> bool:
    """Return True for switch-like OpenHAB items that are not exposed as sensors."""
    return (getattr(item, "oh_type", None) or "").startswith("Switch")
