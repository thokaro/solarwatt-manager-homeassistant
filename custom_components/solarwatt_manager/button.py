from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SOLARWATTDiagnosticsRefreshButton(coordinator, entry.entry_id, entry.title)])


class SOLARWATTDiagnosticsRefreshButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "diagnostics_refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, device_name: str = "SOLARWATT Manager"):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_diagnostics_refresh"

        host = getattr(getattr(self.coordinator, "client", None), "host", None) or entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=device_name,
            manufacturer="SOLARWATT",
            model="Manager flex - rail",
            configuration_url=f"http://{host}",
        )

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_things()
