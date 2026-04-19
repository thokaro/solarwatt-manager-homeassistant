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
    get_registry_entry_device_name,
    get_thing_display_name,
)
from .entity_helpers import (
    build_item_sensor_unique_id,
    iter_item_sensor_names,
    item_sensor_entries,
)
from .naming import (
    compose_entity_object_id,
    item_entity_name,
    slugify_entity_name,
)
from .registry_cleanup import cleanup_empty_channel_thing_diagnostics

_LOGGER = logging.getLogger(__name__)
_PENDING_REGISTRY_MIGRATIONS = f"{DOMAIN}_pending_registry_migrations"


def finalize_registry_migrations(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None,
    things: Mapping[str, Any] | None,
    *,
    force_entity_id_rebuild: bool = False,
) -> None:
    """Run all registry migrations that require entities to exist already."""
    migrate_item_entities_to_thing_devices(hass, entry, items, item_to_thing_uid)
    migrate_item_sensor_entity_ids(
        hass,
        entry,
        items,
        item_to_thing_uid,
        things,
        force_rebuild=force_entity_id_rebuild,
    )
    cleanup_empty_channel_thing_diagnostics(
        hass,
        entry,
        things,
    )
    cleanup_legacy_device_registry_entries(hass, entry)


def mark_pending_registry_migration(hass: HomeAssistant, entry_id: str) -> None:
    """Remember that the next setup should finalize registry migrations."""
    pending = hass.data.setdefault(_PENDING_REGISTRY_MIGRATIONS, set())
    pending.add(entry_id)


def consume_pending_registry_migration(hass: HomeAssistant, entry_id: str) -> bool:
    """Return and clear whether the next setup should finalize registry migrations."""
    pending = hass.data.get(_PENDING_REGISTRY_MIGRATIONS)
    if not pending or entry_id not in pending:
        return False
    pending.discard(entry_id)
    if not pending:
        hass.data.pop(_PENDING_REGISTRY_MIGRATIONS, None)
    return True


def cleanup_legacy_device_registry_entries(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
) -> None:
    """Remove obsolete registry entries left behind by older releases."""
    ent_reg = er.async_get(hass)
    legacy_unique_ids = {
        f"{entry.entry_id}_diagnostics_refresh",
        f"{entry.entry_id}_rebuild_entity_names",
    }
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


def migrate_item_sensor_entity_ids(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None,
    things: Mapping[str, Any] | None,
    *,
    force_rebuild: bool = False,
) -> None:
    """Migrate item sensor entity IDs to the current device-name based format."""
    ent_reg, entries = item_sensor_entries(hass, entry)
    if not entries:
        return

    parameters = _update_entity_parameters(ent_reg)
    if "new_entity_id" not in parameters:
        _LOGGER.debug("Entity registry does not support entity_id migration for entry %s", entry.entry_id)
        return

    host = str(entry.data.get("host") or "").strip().lower()
    dev_reg = dr.async_get(hass)
    migrated = 0
    skipped = 0
    collisions = 0

    for registry_entry in entries:
        item_name = _item_name_from_unique_id(entry, registry_entry.unique_id)
        if not item_name or item_name not in (items or {}):
            continue

        device_name = _target_device_name(
            dev_reg,
            registry_entry.device_id,
            host,
            item_name,
            item_to_thing_uid,
            things,
            entry.title,
        )
        entity_name = item_entity_name(item_name)
        entity_slug = slugify_entity_name(entity_name)
        target_object_id = compose_entity_object_id(device_name, entity_name)
        current_object_id = registry_entry.entity_id.removeprefix("sensor.")

        if not target_object_id or current_object_id == target_object_id:
            continue
        if not force_rebuild and not _should_migrate_entity_id(current_object_id, entity_slug):
            skipped += 1
            continue

        target_entity_id = f"sensor.{target_object_id}"
        existing_entry = ent_reg.async_get(target_entity_id)
        if existing_entry and existing_entry.entity_id != registry_entry.entity_id:
            collisions += 1
            _LOGGER.warning(
                "Skipping entity_id migration for %s due to collision: %s",
                registry_entry.entity_id,
                target_entity_id,
            )
            continue

        ent_reg.async_update_entity(
            registry_entry.entity_id,
            new_entity_id=target_entity_id,
        )
        migrated += 1

    if migrated or skipped or collisions:
        _LOGGER.info(
            "Entity ID migration finished for entry %s: migrated=%s skipped=%s collisions=%s",
            entry.entry_id,
            migrated,
            skipped,
            collisions,
        )


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

    ent_reg, entries = item_sensor_entries(hass, entry)
    entries_by_unique_id = {
        registry_entry.unique_id: registry_entry
        for registry_entry in entries
        if registry_entry.unique_id
    }
    if not entries_by_unique_id:
        return

    dev_reg = dr.async_get(hass)
    moved = 0
    for item_name in iter_item_sensor_names(items):
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


def _update_entity_device(
    ent_reg: er.EntityRegistry,
    entity_id: str,
    target_device_id: str,
) -> bool:
    """Update a registry entry to point at a different device if supported."""
    parameters = _update_entity_parameters(ent_reg)

    if "device_id" in parameters:
        ent_reg.async_update_entity(entity_id, device_id=target_device_id)
        return True
    if "new_device_id" in parameters:
        ent_reg.async_update_entity(entity_id, new_device_id=target_device_id)
        return True

    _LOGGER.debug("Entity registry does not support device migration for %s", entity_id)
    return False


def _update_entity_parameters(ent_reg: er.EntityRegistry) -> Mapping[str, inspect.Parameter]:
    """Return the parameters of ``async_update_entity`` if available."""
    try:
        return inspect.signature(ent_reg.async_update_entity).parameters
    except (TypeError, ValueError):
        return {}


def _item_name_from_unique_id(entry: SOLARWATTConfigEntry, unique_id: str | None) -> str | None:
    """Return the raw item name encoded in the sensor unique_id."""
    if not unique_id:
        return None
    prefix = f"{entry.entry_id}_"
    if not unique_id.startswith(prefix):
        return None
    item_name = unique_id.removeprefix(prefix)
    return item_name or None


def _target_device_name(
    dev_reg: dr.DeviceRegistry,
    registry_device_id: str | None,
    host: str,
    item_name: str,
    item_to_thing_uid: Mapping[str, str] | None,
    things: Mapping[str, Any] | None,
    fallback_device_name: str,
) -> str:
    """Return the current device name that should be used for the entity_id."""
    if registry_name := get_registry_entry_device_name(
        dev_reg.async_get(registry_device_id) if registry_device_id else None
    ):
        return registry_name

    thing_uid = (item_to_thing_uid or {}).get(item_name)
    if thing_uid and host:
        if registry_name := get_registry_entry_device_name(
            dev_reg.async_get_device(
                identifiers={build_thing_device_identifier(host, thing_uid)}
            )
        ):
            return registry_name

    thing = (things or {}).get(thing_uid or "")
    if isinstance(thing, Mapping):
        thing_name = get_thing_display_name(thing, fallback_device_name)
        if thing_name:
            return thing_name

    return fallback_device_name


def _should_migrate_entity_id(current_object_id: str, entity_slug: str) -> bool:
    """Return True when the current object_id looks auto-generated for this item."""
    if not current_object_id or not entity_slug:
        return False
    return (
        current_object_id == entity_slug
        or current_object_id.endswith(f"_{entity_slug}")
    )
