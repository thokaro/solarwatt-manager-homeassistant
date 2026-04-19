from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any, TypeVar

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    SOLARWATTConfigEntry,
    build_thing_device_identifier,
    build_thing_device_info,
    get_disable_duplicate_item_entities,
    get_preferred_parent_thing_uid,
    get_selected_thing_uids,
)
from .naming import clean_item_key

_ThingEntityT = TypeVar("_ThingEntityT")


# Item helpers.
def build_item_sensor_unique_id(entry_id: str, item_name: str) -> str:
    """Return the stable unique_id for an item sensor."""
    return f"{entry_id}_{clean_item_key(item_name or '')}"


def build_thing_sensor_unique_id(entry_id: str, thing_uid: str) -> str:
    """Return the stable unique_id for a thing diagnostics sensor."""
    return f"{entry_id}_thing_{thing_uid}"


def build_thing_diagnostics_refresh_unique_id(entry_id: str, thing_uid: str) -> str:
    """Return the stable unique_id for a thing diagnostics refresh button."""
    return f"{build_thing_sensor_unique_id(entry_id, thing_uid)}_diagnostics_refresh"


def is_switch_item(item: Any) -> bool:
    """Return True for switch-like OpenHAB items that are not exposed as sensors."""
    return (getattr(item, "oh_type", None) or "").startswith("Switch")


def iter_item_sensor_names(
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None = None,
    selected_thing_uids: set[str] | None = None,
) -> Iterator[str]:
    """Yield non-switch item names that match the selected devices."""
    for item_name, item in (items or {}).items():
        if is_switch_item(item):
            continue
        thing_uid = (item_to_thing_uid or {}).get(item_name)
        if (
            selected_thing_uids is not None
            and thing_uid is not None
            and thing_uid not in selected_thing_uids
        ):
            continue
        yield item_name


def iter_selected_item_sensor_names(
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None = None,
    selected_thing_uids: set[str] | None = None,
    duplicate_item_targets: Mapping[str, str] | None = None,
    disable_duplicate_item_entities: bool = False,
) -> Iterator[str]:
    """Yield coordinator item names that should be exposed as sensors."""
    for item_name in iter_item_sensor_names(items, item_to_thing_uid, selected_thing_uids):
        if (
            disable_duplicate_item_entities
            and item_name in (duplicate_item_targets or {})
        ):
            continue
        yield item_name


def collect_new_thing_entities(
    things: Mapping[str, dict[str, Any]] | None,
    selected_thing_uids: set[str] | None,
    added_thing_uids: set[str],
    entity_factory: Callable[[str, dict[str, Any]], _ThingEntityT],
) -> list[_ThingEntityT]:
    """Build thing-bound entities that were not added before."""
    entities: list[_ThingEntityT] = []
    for thing_uid, thing in (things or {}).items():
        if selected_thing_uids is not None and thing_uid not in selected_thing_uids:
            continue
        if thing_uid in added_thing_uids:
            continue
        added_thing_uids.add(thing_uid)
        entities.append(entity_factory(thing_uid, thing))
    return entities


def _thing_entity_unique_ids(entry_id: str, thing_uid: str) -> tuple[str, str]:
    """Return the managed entity unique_ids for one thing."""
    return (
        build_thing_sensor_unique_id(entry_id, thing_uid),
        build_thing_diagnostics_refresh_unique_id(entry_id, thing_uid),
    )


def _selected_entity_unique_ids(
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None,
    selected_thing_uids: set[str],
    things: Mapping[str, Any] | None,
    duplicate_item_targets: Mapping[str, str] | None = None,
    disable_duplicate_item_entities: bool = False,
) -> set[str]:
    """Return the expected active entity unique IDs for the selected devices."""
    expected_unique_ids = {
        build_item_sensor_unique_id(entry.entry_id, item_name)
        for item_name in iter_selected_item_sensor_names(
            items,
            item_to_thing_uid,
            selected_thing_uids,
            duplicate_item_targets,
            disable_duplicate_item_entities,
        )
    }

    for thing_uid in (things or {}).keys():
        if thing_uid not in selected_thing_uids:
            continue
        expected_unique_ids.update(_thing_entity_unique_ids(entry.entry_id, thing_uid))

    return expected_unique_ids


# Entity-registry helpers.
def _managed_registry_entries(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    *,
    domains: set[str] | None = None,
) -> tuple[er.EntityRegistry, list[er.RegistryEntry]]:
    """Return managed SOLARWATT registry entries for one config entry."""
    ent_reg = er.async_get(hass)
    entries = [
        registry_entry
        for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if registry_entry.platform == DOMAIN
        and registry_entry.unique_id
        and (domains is None or registry_entry.domain in domains)
    ]
    return ent_reg, entries


def item_sensor_entries(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry
) -> tuple[er.EntityRegistry, list[er.RegistryEntry]]:
    """Return sensor registry entries for this config entry excluding thing diagnostics."""
    ent_reg, managed_entries = _managed_registry_entries(hass, entry, domains={"sensor"})
    thing_prefix = f"{entry.entry_id}_thing_"
    entries = [
        registry_entry
        for registry_entry in managed_entries
        if not registry_entry.unique_id.startswith(thing_prefix)
    ]
    return ent_reg, entries


def _apply_expected_entity_selection(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    expected_unique_ids: set[str],
) -> None:
    """Enable expected entities and disable managed entities outside the selection."""
    ent_reg, entries = _managed_registry_entries(hass, entry, domains={"sensor", "button"})
    managed_prefix = f"{entry.entry_id}_"
    for registry_entry in entries:
        if registry_entry.unique_id in expected_unique_ids:
            if registry_entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
                ent_reg.async_update_entity(registry_entry.entity_id, disabled_by=None)
            continue

        if registry_entry.disabled_by == er.RegistryEntryDisabler.USER:
            continue
        if not registry_entry.unique_id.startswith(managed_prefix):
            continue

        ent_reg.async_update_entity(
            registry_entry.entity_id,
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )


# Device-registry helpers.
def ensure_parent_devices_registered(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    things: Mapping[str, Any] | None,
) -> None:
    """Pre-register visible parent devices so child entities can safely reference `via_device`."""
    host = str(entry.data.get("host") or "").strip().lower()
    if not host:
        return

    selected_thing_uids = get_selected_thing_uids(entry.options)
    things_by_uid = {
        str(uid).strip(): thing
        for uid, thing in (things or {}).items()
        if str(uid).strip() and isinstance(thing, dict)
    }
    dev_reg = dr.async_get(hass)
    parent_uids = {
        parent_uid
        for thing_uid, thing in things_by_uid.items()
        if selected_thing_uids is None or thing_uid in selected_thing_uids
        if (parent_uid := get_preferred_parent_thing_uid(thing, things_by_uid))
        if selected_thing_uids is None or parent_uid in selected_thing_uids
    }

    for parent_uid in parent_uids:
        parent_thing = things_by_uid.get(parent_uid)
        if parent_thing is None:
            continue

        device_info = build_thing_device_info(
            hass,
            host,
            parent_thing,
            things_by_uid,
            selected_thing_uids,
        )
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            **{
                key: value
                for key, value in device_info.items()
                if value is not None
            },
        )


def detach_entityless_thing_devices(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    things: Mapping[str, Any] | None,
) -> None:
    """Detach this config entry from thing devices that have no managed entities."""
    host = str(entry.data.get("host") or "").strip().lower()
    if not host:
        return

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    managed_device_ids = {
        registry_entry.device_id
        for registry_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if registry_entry.platform == DOMAIN and registry_entry.device_id
    }

    for thing_uid in (things or {}).keys():
        device = dev_reg.async_get_device(
            identifiers={build_thing_device_identifier(host, thing_uid)}
        )
        if not device or entry.entry_id not in device.config_entries:
            continue
        if device.id in managed_device_ids:
            continue
        dev_reg.async_update_device(device_id=device.id, remove_config_entry_id=entry.entry_id)


def _sync_thing_device_assignments(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    things: Mapping[str, Any] | None,
    selected_thing_uids: set[str] | None,
) -> None:
    """Attach or detach this config entry on thing devices based on selection."""
    host = str(entry.data.get("host") or "").strip().lower()
    if not host:
        return

    dev_reg = dr.async_get(hass)
    for thing_uid in (things or {}).keys():
        device = dev_reg.async_get_device(
            identifiers={build_thing_device_identifier(host, thing_uid)}
        )
        if not device:
            continue
        is_selected = selected_thing_uids is None or thing_uid in selected_thing_uids
        has_entry = entry.entry_id in device.config_entries
        if is_selected and not has_entry:
            dev_reg.async_update_device(
                device_id=device.id,
                add_config_entry_id=entry.entry_id,
            )
        elif not is_selected and has_entry:
            dev_reg.async_update_device(
                device_id=device.id,
                remove_config_entry_id=entry.entry_id,
            )


# Public orchestration.
def sync_selected_thing_entities(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    items: Mapping[str, Any] | None,
    item_to_thing_uid: Mapping[str, str] | None,
    things: Mapping[str, Any] | None,
    duplicate_item_targets: Mapping[str, str] | None = None,
    options: Mapping[str, Any] | None = None,
) -> None:
    """Enable selected devices and disable deselected ones in the entity registry."""
    resolved_options = options if options is not None else entry.options
    selected_thing_uids = get_selected_thing_uids(resolved_options)
    disable_duplicate_item_entities = get_disable_duplicate_item_entities(resolved_options)
    if selected_thing_uids is None:
        selected_thing_uids = set((things or {}).keys())
        expected_unique_ids = _selected_entity_unique_ids(
            entry,
            items,
            item_to_thing_uid,
            selected_thing_uids,
            things,
            duplicate_item_targets,
            disable_duplicate_item_entities,
        )
        _apply_expected_entity_selection(hass, entry, expected_unique_ids)
        _sync_thing_device_assignments(hass, entry, things, None)
        return

    expected_unique_ids = _selected_entity_unique_ids(
        entry,
        items,
        item_to_thing_uid,
        selected_thing_uids,
        things,
        duplicate_item_targets,
        disable_duplicate_item_entities,
    )
    _apply_expected_entity_selection(hass, entry, expected_unique_ids)
    _sync_thing_device_assignments(hass, entry, things, selected_thing_uids)
