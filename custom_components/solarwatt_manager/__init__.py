from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import SOLARWATTCoordinator, SOLARWATTClient
from .naming import clean_item_key, normalize_item_name

PLATFORMS: list[str] = ["sensor", "button"]
_LOGGER = logging.getLogger(__name__)


def _migrate_sensor_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: SOLARWATTCoordinator
) -> None:
    """Migrate sensor unique IDs from normalized item names to raw item names."""
    migration_map: dict[str, str] = {}
    for item_name, item in (coordinator.data or {}).items():
        if (getattr(item, "oh_type", None) or "").startswith("Switch"):
            continue

        old_unique_id = f"{entry.entry_id}_{normalize_item_name(item_name or '')}"
        new_unique_id = f"{entry.entry_id}_{clean_item_key(item_name or '')}"
        if old_unique_id != new_unique_id:
            migration_map[old_unique_id] = new_unique_id

    if not migration_map:
        return

    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    used_unique_ids = {ent.unique_id for ent in entries if ent.unique_id}

    migrated = 0
    skipped = 0
    for ent in entries:
        if ent.domain != "sensor" or ent.platform != DOMAIN:
            continue

        target_unique_id = migration_map.get(ent.unique_id)
        if not target_unique_id:
            continue
        if target_unique_id in used_unique_ids and target_unique_id != ent.unique_id:
            skipped += 1
            _LOGGER.warning(
                "Skipping unique_id migration for %s due to collision: %s",
                ent.entity_id,
                target_unique_id,
            )
            continue

        ent_reg.async_update_entity(ent.entity_id, new_unique_id=target_unique_id)
        used_unique_ids.discard(ent.unique_id)
        used_unique_ids.add(target_unique_id)
        migrated += 1

    if migrated or skipped:
        _LOGGER.info(
            "Unique ID migration finished for entry %s: migrated=%s skipped=%s",
            entry.entry_id,
            migrated,
            skipped,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = str(entry.data["host"]).strip().lower()
    username = entry.data["username"]
    password = entry.data["password"]

    client = SOLARWATTClient(hass, host=host, username=username, password=password)
    coordinator = SOLARWATTCoordinator(hass, entry, client)
    coordinator_registered = False

    try:
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_refresh_things()
        _migrate_sensor_unique_ids(hass, entry, coordinator)

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        coordinator_registered = True

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        if coordinator_registered:
            hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        await client.async_close()
        raise

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator:
            await coordinator.client.async_close()
    return unload_ok
