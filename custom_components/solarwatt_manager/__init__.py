from __future__ import annotations

from homeassistant.core import HomeAssistant

from .client import SOLARWATTClient
from .const import CONFIG_ENTRY_VERSION, SOLARWATTConfigEntry
from .coordinator import SOLARWATTCoordinator
from .entity_helpers import (
    detach_entityless_thing_devices,
    ensure_parent_devices_registered,
    sync_selected_thing_entities,
)
from .registry_cleanup import cleanup_empty_channel_thing_diagnostics
from .registry_migrations import migrate_device_registry_identifiers
from .services import async_register_services
from .stats_total import StatsTotalStore

PLATFORMS: list[str] = ["sensor", "button", "select", "switch"]


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: SOLARWATTConfigEntry,
) -> bool:
    """Migrate config-entry schema before setup discovers the stable installation ID."""
    if entry.version > CONFIG_ENTRY_VERSION:
        return False
    if entry.version < CONFIG_ENTRY_VERSION:
        hass.config_entries.async_update_entry(
            entry,
            version=CONFIG_ENTRY_VERSION,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SOLARWATTConfigEntry) -> bool:
    host = str(entry.data.get("host") or "").strip().lower()
    username = str(entry.data.get("username") or "")
    password = str(entry.data.get("password") or "")
    client = SOLARWATTClient(hass, host=host, username=username, password=password)
    coordinator = SOLARWATTCoordinator(hass, entry, client)
    coordinator.stats_total_store = StatsTotalStore(hass, entry.entry_id)
    runtime_data_set = False

    try:
        await coordinator.stats_total_store.async_load()
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_refresh_things(prefer_hems_cache=True)
        migrate_device_registry_identifiers(hass, entry, coordinator.things)

        sync_selected_thing_entities(
            hass,
            entry,
            coordinator.data,
            coordinator.item_to_thing_uid,
            coordinator.things,
            coordinator.duplicate_item_targets,
        )
        ensure_parent_devices_registered(hass, entry, coordinator.things)

        entry.runtime_data = coordinator
        runtime_data_set = True

        async_register_services(hass)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        detach_entityless_thing_devices(hass, entry, coordinator.things)

        cleanup_empty_channel_thing_diagnostics(
            hass,
            entry,
            coordinator.things,
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
            if coordinator.stats_total_store is not None:
                await coordinator.stats_total_store.async_save()
            await coordinator.client.async_close()
        entry.runtime_data = None
    return unload_ok
