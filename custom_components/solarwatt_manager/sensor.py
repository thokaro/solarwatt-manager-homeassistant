from __future__ import annotations

import re

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_ALL_SENSORS, CONF_NAME_PREFIX, DEFAULT_ENABLE_ALL_SENSORS, DOMAIN
from .naming import format_display_name, is_enabled_by_default, normalize_item_name
from .coordinator import guess_ha_meta




# Enable only a small set of "core" sensors by default. Serial numbers in the
# item name can differ between installations, so we match with regex.


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    prefix = (entry.options.get(CONF_NAME_PREFIX) or "").strip()
    enable_all = entry.options.get(CONF_ENABLE_ALL_SENSORS, DEFAULT_ENABLE_ALL_SENSORS)

    entities = []
    for item_name in coordinator.data.keys():
        it = coordinator.data[item_name]
        if (it.oh_type or "").startswith("Switch"):
            continue
        entities.append(
            SOLARWATTItemSensor(
                coordinator,
                entry.entry_id,
                item_name,
                device_name=entry.title,
                prefix=prefix,
                enable_all=enable_all,
            )
        )

    for thing_uid, thing in (getattr(coordinator, "things", {}) or {}).items():
        entities.append(
            SOLARWATTThingSensor(
                coordinator,
                entry.entry_id,
                thing_uid,
                thing,
                device_name=entry.title,
            )
        )

    async_add_entities(entities)


class SOLARWATTItemSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator,
        entry_id: str,
        item_name: str,
        device_name: str = "SOLARWATT Manager",
        prefix: str = "",
        enable_all: bool = False,
    ):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._item_name = item_name

        clean_item_name = normalize_item_name(item_name or "")
        self._clean_item_name = clean_item_name
        self._prefix = prefix

        self._attr_unique_id = f"{entry_id}_{clean_item_name}"
        self._attr_entity_registry_enabled_default = enable_all or is_enabled_by_default(self._item_name)

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
        display_name = format_display_name(base_name)
        self._attr_name = f"{prefix} {display_name}".strip() if prefix else display_name

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


class SOLARWATTThingSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator,
        entry_id: str,
        thing_uid: str,
        thing: dict,
        device_name: str = "SOLARWATT Manager",
    ):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._thing_uid = thing_uid
        self._attr_unique_id = f"{entry_id}_thing_{thing_uid}"

        label = (thing.get("label") or thing_uid or "").strip()
        self._attr_name = label or thing_uid

        host = getattr(getattr(self.coordinator, "client", None), "host", None) or entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=device_name,
            manufacturer="SOLARWATT",
            model="Manager flex - rail",
            configuration_url=f"http://{host}",
        )

    def _thing(self) -> dict | None:
        return (getattr(self.coordinator, "things", {}) or {}).get(self._thing_uid)

    @property
    def native_value(self):
        thing = self._thing()
        if not thing:
            return None
        status = (thing.get("statusInfo") or {}).get("status")
        return status or None

    @property
    def extra_state_attributes(self):
        thing = self._thing()
        if not thing:
            return {}
        props = thing.get("properties")
        return props if isinstance(props, dict) else {}
