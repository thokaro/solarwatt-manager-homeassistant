from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ENABLE_ALL_SENSORS,
    DEFAULT_ENABLE_ALL_SENSORS,
    DOMAIN,
    OPT_ENABLED_SENSOR_IDS_BEFORE_ALL,
    SOLARWATTConfigEntry,
)
from .naming import clean_item_key, is_enabled_by_default, normalize_item_name

_LOGGER = logging.getLogger(__name__)


def build_item_sensor_unique_id(entry_id: str, item_name: str) -> str:
    """Return the stable unique_id for an item sensor."""
    return f"{entry_id}_{clean_item_key(item_name or '')}"


def build_legacy_item_sensor_unique_id(entry_id: str, item_name: str) -> str:
    """Return the legacy normalized unique_id used before the raw-key migration."""
    return f"{entry_id}_{normalize_item_name(item_name or '')}"


def is_item_sensor_enabled_by_default(
    item_name: str, enable_all: bool = False
) -> bool:
    """Return whether an item sensor should be enabled by default."""
    return enable_all or is_enabled_by_default(item_name)


def migrate_item_sensor_unique_ids(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
) -> None:
    """Migrate item sensor unique IDs from normalized names to raw item names."""
    migration_map: dict[str, str] = {}
    for item_name in _item_sensor_names(items):
        old_unique_id = build_legacy_item_sensor_unique_id(entry.entry_id, item_name)
        new_unique_id = build_item_sensor_unique_id(entry.entry_id, item_name)
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


def enable_all_item_sensor_entities(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
) -> None:
    """Enable item sensor entities previously disabled by the integration."""
    if not entry.options.get(CONF_ENABLE_ALL_SENSORS, DEFAULT_ENABLE_ALL_SENSORS):
        return

    expected_unique_ids = {
        build_item_sensor_unique_id(entry.entry_id, item_name)
        for item_name in _item_sensor_names(items)
    }
    if not expected_unique_ids:
        return

    ent_reg, entries = _item_sensor_entries(hass, entry)
    enabled = 0
    for registry_entry in entries:
        if registry_entry.unique_id not in expected_unique_ids:
            continue
        if registry_entry.disabled_by != er.RegistryEntryDisabler.INTEGRATION:
            continue

        ent_reg.async_update_entity(registry_entry.entity_id, disabled_by=None)
        enabled += 1

    if enabled:
        _LOGGER.info(
            "Enabled %s SOLARWATT sensor entities disabled by integration for entry %s",
            enabled,
            entry.entry_id,
        )


def sync_enable_all_item_sensor_entities(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    data: dict[str, Any],
) -> None:
    """Persist and apply the enable-all-sensors transition."""
    old_enable_all = entry.options.get(
        CONF_ENABLE_ALL_SENSORS, DEFAULT_ENABLE_ALL_SENSORS
    )
    new_enable_all = data.get(CONF_ENABLE_ALL_SENSORS, DEFAULT_ENABLE_ALL_SENSORS)
    keep_enabled_ids = set(entry.options.get(OPT_ENABLED_SENSOR_IDS_BEFORE_ALL, []))

    if new_enable_all and not old_enable_all:
        data[OPT_ENABLED_SENSOR_IDS_BEFORE_ALL] = sorted(
            _enabled_item_sensor_unique_ids(hass, entry)
        )
        return

    if not new_enable_all and old_enable_all:
        _disable_auto_enabled_item_sensor_entities(hass, entry, keep_enabled_ids)
        data[OPT_ENABLED_SENSOR_IDS_BEFORE_ALL] = []
        return

    data[OPT_ENABLED_SENSOR_IDS_BEFORE_ALL] = (
        sorted(keep_enabled_ids) if new_enable_all else []
    )


def _enabled_item_sensor_unique_ids(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry
) -> set[str]:
    """Return item sensor unique IDs that are currently enabled."""
    _, entries = _item_sensor_entries(hass, entry)
    return {
        registry_entry.unique_id
        for registry_entry in entries
        if registry_entry.disabled_by is None
    }


def _disable_auto_enabled_item_sensor_entities(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    keep_enabled_ids: set[str],
) -> None:
    """Disable sensors that became active only because enable-all was enabled."""
    ent_reg, entries = _item_sensor_entries(hass, entry)
    for registry_entry in entries:
        if registry_entry.unique_id in keep_enabled_ids:
            continue
        if _is_default_enabled_item_sensor(entry, registry_entry.unique_id):
            continue
        if registry_entry.disabled_by in (
            er.RegistryEntryDisabler.USER,
            er.RegistryEntryDisabler.INTEGRATION,
        ):
            continue

        ent_reg.async_update_entity(
            registry_entry.entity_id,
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )


def _is_default_enabled_item_sensor(
    entry: SOLARWATTConfigEntry, unique_id: str
) -> bool:
    """Return whether the registry unique_id belongs to a default-enabled item sensor."""
    prefix = f"{entry.entry_id}_"
    if not unique_id.startswith(prefix):
        return False
    return is_item_sensor_enabled_by_default(unique_id.removeprefix(prefix))


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
