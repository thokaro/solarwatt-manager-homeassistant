from __future__ import annotations

import re

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME_PREFIX, DOMAIN
from .naming import is_enabled_by_default, normalize_item_name
from .coordinator import guess_ha_meta




# Enable only a small set of "core" sensors by default. Serial numbers in the
# item name can differ between installations, so we match with regex.


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    prefix = (entry.options.get(CONF_NAME_PREFIX) or "").strip()

    entities = []
    for item_name in coordinator.data.keys():
        it = coordinator.data[item_name]
        if (it.oh_type or "").startswith("Switch"):
            continue
        entities.append(SOLARWATTItemSensor(coordinator, entry.entry_id, item_name, device_name=entry.title, prefix=prefix))

    async_add_entities(entities)


class SOLARWATTItemSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = False

    def __init__(self, coordinator, entry_id: str, item_name: str, device_name: str = "SOLARWATT Manager", prefix: str = ""):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._item_name = item_name

        clean_item_name = normalize_item_name(item_name or "")
        self._clean_item_name = clean_item_name
        self._prefix = prefix

        self._attr_unique_id = f"{entry_id}_{clean_item_name}"
        self._attr_entity_registry_enabled_default = is_enabled_by_default(self._item_name)

        # Group all sensors under one device for a cleaner HA UI.
        host = getattr(getattr(self.coordinator, "client", None), "host", None) or entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=device_name,
            manufacturer="SOLARWATT",
            model="Manager flex / rail",
            configuration_url=f"http://{host}",
        )
        item = (self.coordinator.data or {}).get(item_name)

        # Use the OpenHAB/SOLARWATT item name (as requested), strip leading '#',
        # and optionally prefix it.
        base_name = clean_item_name.replace("harmonized_", "").replace("_", " ").strip()
        self._attr_name = f"{prefix} {base_name}".strip() if prefix else base_name

        if item:
            meta = guess_ha_meta(getattr(item, "oh_type", None), getattr(item, "parsed", None), item_name)
            self._attr_device_class = meta.get("device_class")
            self._attr_state_class = meta.get("state_class")
            self._attr_native_unit_of_measurement = meta.get("suggested_unit")
            self._attr_icon = meta.get("icon")

    @property
    def native_value(self):
        item = (self.coordinator.data or {}).get(self._item_name)
        if not item:
            return None
        val = item.parsed.value
        if isinstance(val, str):
            return val.lstrip("#")
        return val
