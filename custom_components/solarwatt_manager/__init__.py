from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SOLARWATTCoordinator, SOLARWATTClient

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data["host"]
    username = entry.data["username"]
    password = entry.data["password"]

    client = SOLARWATTClient(hass, host=host, username=username, password=password)
    coordinator = SOLARWATTCoordinator(hass, entry, client)
    coordinator_registered = False

    try:
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_refresh_things()

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
