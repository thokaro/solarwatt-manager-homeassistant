from __future__ import annotations

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
    get_selected_thing_uids,
)
from .naming import clean_item_key

_LOGGER = logging.getLogger(__name__)


def build_item_sensor_unique_id(entry_id: str, item_name: str) -> str:
    """Return the stable unique_id for an item sensor."""
    return f"{entry_id}_{clean_item_key(item_name or '')}"


def enable_item_sensor_entities(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
) -> None:
    """Enable item sensor entities previously disabled by the integration."""
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


def sync_selected_thing_entities(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None,
    things: Mapping[str, Any] | None,
    options: Mapping[str, Any] | None = None,
) -> None:
    """Enable selected devices and disable deselected ones in the entity registry."""
    selected_thing_uids = get_selected_thing_uids(options if options is not None else entry.options)
    if selected_thing_uids is None:
        enable_item_sensor_entities(hass, entry, items)
        _enable_selected_thing_entities(
            hass,
            entry,
            thing_uids=set((things or {}).keys()),
        )
        _restore_selected_thing_devices(hass, entry, things)
        return

    expected_unique_ids = _selected_entity_unique_ids(
        entry,
        items,
        item_to_thing_uid,
        selected_thing_uids,
        things,
    )
    if not expected_unique_ids:
        _disable_unselected_entities(hass, entry, set())
        _remove_deselected_thing_devices(
            hass,
            entry,
            selected_thing_uids,
            things,
        )
        return

    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    for registry_entry in entries:
        if registry_entry.domain not in {"sensor", "button"}:
            continue
        if registry_entry.platform != DOMAIN or not registry_entry.unique_id:
            continue

        if registry_entry.unique_id in expected_unique_ids:
            if registry_entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
                ent_reg.async_update_entity(registry_entry.entity_id, disabled_by=None)
            continue

        if registry_entry.disabled_by == er.RegistryEntryDisabler.USER:
            continue
        if not _is_managed_entity_unique_id(entry, registry_entry.unique_id):
            continue

        ent_reg.async_update_entity(
            registry_entry.entity_id,
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )

    _remove_deselected_thing_devices(
        hass,
        entry,
        selected_thing_uids,
        things,
    )
def _selected_entity_unique_ids(
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None,
    selected_thing_uids: set[str],
    things: Mapping[str, Any] | None,
) -> set[str]:
    """Return the expected active entity unique IDs for the selected devices."""
    expected_unique_ids: set[str] = set()

    for item_name, item in (items or {}).items():
        if _is_switch_item(item):
            continue
        thing_uid = (item_to_thing_uid or {}).get(item_name)
        if thing_uid and thing_uid not in selected_thing_uids:
            continue
        expected_unique_ids.add(build_item_sensor_unique_id(entry.entry_id, item_name))

    for thing_uid in (things or {}).keys():
        if thing_uid not in selected_thing_uids:
            continue
        expected_unique_ids.add(f"{entry.entry_id}_thing_{thing_uid}")
        expected_unique_ids.add(f"{entry.entry_id}_thing_{thing_uid}_diagnostics_refresh")

    return expected_unique_ids


def _enable_selected_thing_entities(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    thing_uids: set[str],
) -> None:
    """Enable thing sensor/button entities disabled by the integration."""
    ent_reg = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if registry_entry.domain not in {"sensor", "button"}:
            continue
        if registry_entry.platform != DOMAIN or not registry_entry.unique_id:
            continue
        if registry_entry.disabled_by != er.RegistryEntryDisabler.INTEGRATION:
            continue
        if not any(
            registry_entry.unique_id == f"{entry.entry_id}_thing_{thing_uid}"
            or registry_entry.unique_id == f"{entry.entry_id}_thing_{thing_uid}_diagnostics_refresh"
            for thing_uid in thing_uids
        ):
            continue
        ent_reg.async_update_entity(registry_entry.entity_id, disabled_by=None)


def _remove_deselected_thing_devices(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    selected_thing_uids: set[str],
    things: Mapping[str, Any] | None,
) -> None:
    """Remove this config entry from deselected thing devices."""
    host = str(entry.data.get("host") or "").strip().lower()
    if not host:
        return

    dev_reg = dr.async_get(hass)
    for thing_uid in (things or {}).keys():
        if thing_uid in selected_thing_uids:
            continue
        device = dev_reg.async_get_device(
            identifiers={build_thing_device_identifier(host, thing_uid)}
        )
        if not device or entry.entry_id not in device.config_entries:
            continue
        dev_reg.async_update_device(
            device_id=device.id,
            remove_config_entry_id=entry.entry_id,
        )


def _restore_selected_thing_devices(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    things: Mapping[str, Any] | None,
) -> None:
    """Reattach this config entry to selected thing devices if needed."""
    host = str(entry.data.get("host") or "").strip().lower()
    if not host:
        return

    dev_reg = dr.async_get(hass)
    for thing_uid in (things or {}).keys():
        device = dev_reg.async_get_device(
            identifiers={build_thing_device_identifier(host, thing_uid)}
        )
        if not device or entry.entry_id in device.config_entries:
            continue
        dev_reg.async_update_device(
            device_id=device.id,
            add_config_entry_id=entry.entry_id,
        )
def _disable_unselected_entities(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    expected_unique_ids: set[str],
) -> None:
    """Disable managed entities not part of the selected thing set."""
    ent_reg = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if registry_entry.domain not in {"sensor", "button"}:
            continue
        if registry_entry.platform != DOMAIN or not registry_entry.unique_id:
            continue
        if registry_entry.unique_id in expected_unique_ids:
            continue
        if registry_entry.disabled_by == er.RegistryEntryDisabler.USER:
            continue
        if not _is_managed_entity_unique_id(entry, registry_entry.unique_id):
            continue

        ent_reg.async_update_entity(
            registry_entry.entity_id,
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )


def _is_managed_entity_unique_id(entry: SOLARWATTConfigEntry, unique_id: str) -> bool:
    """Return whether the unique_id belongs to a managed SOLARWATT entity."""
    prefix = f"{entry.entry_id}_"
    return unique_id.startswith(prefix)


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
