from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import SOLARWATTConfigEntry
from .coordinator import SOLARWATTCoordinator, SOLARWATTClient
from .entity_helpers import (
    enable_all_item_sensor_entities,
    migrate_item_sensor_unique_ids,
)

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: SOLARWATTConfigEntry) -> bool:
    host = str(entry.data["host"]).strip().lower()
    username = entry.data["username"]
    password = entry.data["password"]

    client = SOLARWATTClient(hass, host=host, username=username, password=password)
    coordinator = SOLARWATTCoordinator(hass, entry, client)
    runtime_data_set = False

    try:
        await coordinator.async_config_entry_first_refresh()
        coordinator.refresh_multi_instance_device_types()
        await coordinator.async_refresh_things()
        migrate_item_sensor_unique_ids(hass, entry, coordinator.data)
        enable_all_item_sensor_entities(hass, entry, coordinator.data)

        entry.runtime_data = coordinator
        runtime_data_set = True

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
