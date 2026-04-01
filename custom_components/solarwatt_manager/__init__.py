from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .client import SOLARWATTClient
from .const import SOLARWATTConfigEntry
from .coordinator import SOLARWATTCoordinator
from .entity_helpers import (
    detach_entityless_thing_devices,
    ensure_parent_devices_registered,
    sync_selected_thing_entities,
)
from .registry_migrations import (
    cleanup_legacy_device_registry_entries,
    consume_pending_registry_migration,
    finalize_registry_migrations,
)

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: SOLARWATTConfigEntry) -> bool:
    host = str(entry.data["host"]).strip().lower()
    username = entry.data["username"]
    password = entry.data["password"]
    ent_reg = er.async_get(hass)
    is_initial_setup = not er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    force_entity_id_rebuild = is_initial_setup or consume_pending_registry_migration(
        hass, entry.entry_id
    )

    client = SOLARWATTClient(hass, host=host, username=username, password=password)
    coordinator = SOLARWATTCoordinator(hass, entry, client)
    runtime_data_set = False

    try:
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_refresh_things()

        if not force_entity_id_rebuild:
            cleanup_legacy_device_registry_entries(hass, entry)

        sync_selected_thing_entities(
            hass,
            entry,
            coordinator.data,
            coordinator.item_to_thing_uid,
            coordinator.things,
        )
        ensure_parent_devices_registered(hass, entry, coordinator.things)

        entry.runtime_data = coordinator
        runtime_data_set = True

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        detach_entityless_thing_devices(hass, entry, coordinator.things)

        if force_entity_id_rebuild:
            finalize_registry_migrations(
                hass,
                entry,
                coordinator.data,
                coordinator.item_to_thing_uid,
                coordinator.things,
                force_entity_id_rebuild=True,
            )
    except Exception:
        if runtime_data_set:
            entry.runtime_data = None
        await client.async_close()
        raise

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: SOLARWATTConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SOLARWATTConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = entry.runtime_data
        if coordinator:
            await coordinator.client.async_close()
        entry.runtime_data = None
    return unload_ok
