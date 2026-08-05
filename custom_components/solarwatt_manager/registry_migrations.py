from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_HOST,
    CONF_INSTALLATION_ID,
    DOMAIN,
    SOLARWATTConfigEntry,
    build_thing_device_identifier,
    derive_installation_id,
    get_device_registry_anchor,
)

_LOGGER = logging.getLogger(__name__)


def migrate_device_registry_identifiers(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
    things: Mapping[str, Any] | None,
) -> None:
    """Migrate host-based device identifiers to the stable installation ID."""
    installation_id = derive_installation_id(entry.data, entry.options, things)
    if installation_id is None:
        return

    duplicate_entry = next(
        (
            configured_entry
            for configured_entry in hass.config_entries.async_entries(DOMAIN)
            if configured_entry.entry_id != entry.entry_id
            and configured_entry.unique_id == installation_id
        ),
        None,
    )
    if duplicate_entry is not None:
        _LOGGER.error(
            "Cannot assign stable SOLARWATT installation ID to entry %s because entry %s already uses it",
            entry.entry_id,
            duplicate_entry.entry_id,
        )
        return

    previous_anchor = get_device_registry_anchor(entry)
    old_anchors = {
        previous_anchor,
        str(entry.data.get(CONF_HOST) or "").strip().lower(),
        str(entry.unique_id or "").strip(),
        entry.entry_id,
    }
    old_anchors.discard("")
    old_anchors.discard(installation_id)

    thing_uids = {
        uid
        for key, thing in (things or {}).items()
        for uid in (
            str(key).strip(),
            str(
                thing.get("UID") or thing.get("uid") or ""
                if isinstance(thing, Mapping)
                else ""
            ).strip(),
        )
        if uid
    }
    identifiers_by_anchor = {
        anchor: (
            (DOMAIN, anchor),
            *(build_thing_device_identifier(anchor, thing_uid) for thing_uid in thing_uids),
        )
        for anchor in old_anchors
    }

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    migrated = 0
    for old_anchor, old_identifiers in identifiers_by_anchor.items():
        for old_identifier in old_identifiers:
            suffix = old_identifier[1].removeprefix(old_anchor)
            new_identifier = (DOMAIN, f"{installation_id}{suffix}")
            migrated += _migrate_device_identifier(
                dev_reg,
                ent_reg,
                entry,
                registry_entries,
                old_identifier,
                new_identifier,
            )

    data = dict(entry.data)
    data[CONF_INSTALLATION_ID] = installation_id
    if data != dict(entry.data) or entry.unique_id != installation_id:
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            unique_id=installation_id,
        )

    if migrated:
        _LOGGER.info(
            "Migrated %s SOLARWATT devices to the stable installation ID for entry %s",
            migrated,
            entry.entry_id,
        )


def _migrate_device_identifier(
    dev_reg: dr.DeviceRegistry,
    ent_reg: er.EntityRegistry,
    entry: SOLARWATTConfigEntry,
    registry_entries: list[er.RegistryEntry],
    old_identifier: tuple[str, str],
    new_identifier: tuple[str, str],
) -> int:
    """Replace one device identifier and merge an already-created target device."""
    old_device = dev_reg.async_get_device(identifiers={old_identifier})
    if old_device is None:
        return 0

    target_device = dev_reg.async_get_device(identifiers={new_identifier})
    if target_device is not None and target_device.id != old_device.id:
        if entry.entry_id not in target_device.config_entries:
            dev_reg.async_update_device(
                device_id=target_device.id,
                add_config_entry_id=entry.entry_id,
            )
        for registry_entry in registry_entries:
            if registry_entry.device_id == old_device.id:
                ent_reg.async_update_entity(
                    registry_entry.entity_id,
                    device_id=target_device.id,
                )
        if entry.entry_id in old_device.config_entries:
            dev_reg.async_update_device(
                device_id=old_device.id,
                remove_config_entry_id=entry.entry_id,
            )
        return 1

    identifiers = set(old_device.identifiers)
    identifiers.discard(old_identifier)
    identifiers.add(new_identifier)
    dev_reg.async_update_device(
        device_id=old_device.id,
        new_identifiers=identifiers,
    )
    return 1
