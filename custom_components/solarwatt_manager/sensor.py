from __future__ import annotations

import math

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_NAME_PREFIX,
    CONF_ENERGY_DELTA_KWH,
    DEFAULT_ENERGY_DELTA_KWH,
    SOLARWATTConfigEntry,
    build_device_info,
    build_thing_device_info,
    get_selected_thing_uids,
    get_thing_display_name,
)
from .entity_helpers import (
    build_item_sensor_unique_id,
)
from .naming import format_display_name, normalize_item_name
from .sensor_meta import guess_ha_meta


async def async_setup_entry(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = entry.runtime_data

    prefix = (entry.options.get(CONF_NAME_PREFIX) or "").strip()
    energy_delta_kwh = float(entry.options.get(CONF_ENERGY_DELTA_KWH, DEFAULT_ENERGY_DELTA_KWH))

    entities = []
    added_item_names: set[str] = set()
    added_thing_uids: set[str] = set()
    selected_thing_uids = get_selected_thing_uids(entry.options)
    for item_name, it in coordinator.data.items():
        if (it.oh_type or "").startswith("Switch"):
            continue
        thing_uid = (getattr(coordinator, "item_to_thing_uid", {}) or {}).get(item_name)
        if (
            thing_uid
            and selected_thing_uids is not None
            and thing_uid not in selected_thing_uids
        ):
            continue
        added_item_names.add(item_name)
        entities.append(
            SOLARWATTItemSensor(
                coordinator,
                entry.entry_id,
                item_name,
                device_name=entry.title,
                prefix=prefix,
                energy_delta_kwh=energy_delta_kwh,
            )
        )

    for thing_uid, thing in (getattr(coordinator, "things", {}) or {}).items():
        if selected_thing_uids is not None and thing_uid not in selected_thing_uids:
            continue
        added_thing_uids.add(thing_uid)
        entities.append(
            SOLARWATTThingSensor(
                coordinator,
                entry.entry_id,
                thing_uid,
                thing,
            )
        )

    async_add_entities(entities)

    @callback
    def _async_discover_new_entities() -> None:
        new_entities: list[SensorEntity] = []
        for item_name, it in (coordinator.data or {}).items():
            if (it.oh_type or "").startswith("Switch"):
                continue
            thing_uid = (getattr(coordinator, "item_to_thing_uid", {}) or {}).get(item_name)
            if (
                thing_uid
                and selected_thing_uids is not None
                and thing_uid not in selected_thing_uids
            ):
                continue
            if item_name in added_item_names:
                continue
            added_item_names.add(item_name)
            new_entities.append(
                SOLARWATTItemSensor(
                    coordinator,
                    entry.entry_id,
                    item_name,
                    device_name=entry.title,
                    prefix=prefix,
                    energy_delta_kwh=energy_delta_kwh,
                )
            )

        for thing_uid, thing in (getattr(coordinator, "things", {}) or {}).items():
            if selected_thing_uids is not None and thing_uid not in selected_thing_uids:
                continue
            if thing_uid in added_thing_uids:
                continue
            added_thing_uids.add(thing_uid)
            new_entities.append(
                SOLARWATTThingSensor(
                    coordinator,
                    entry.entry_id,
                    thing_uid,
                    thing,
                )
            )
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.register_discovery_callback(_async_discover_new_entities))


class SOLARWATTItemSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator,
        entry_id: str,
        item_name: str,
        device_name: str = "SOLARWATT Manager",
        prefix: str = "",
        energy_delta_kwh: float = DEFAULT_ENERGY_DELTA_KWH,
    ):
        super().__init__(coordinator)
        self._item_name = item_name
        self._energy_delta_kwh = energy_delta_kwh
        self._last_energy_value: float | None = None
        self._last_update_success: bool | None = None
        self._is_energy = False
        self._prefix = prefix

        self._attr_unique_id = build_item_sensor_unique_id(entry_id, item_name)
        self._attr_entity_registry_enabled_default = True

        host = getattr(getattr(self.coordinator, "client", None), "host", None) or entry_id
        thing_uid = (getattr(self.coordinator, "item_to_thing_uid", {}) or {}).get(item_name)
        thing = (getattr(self.coordinator, "things", {}) or {}).get(thing_uid) if thing_uid else None
        self._attr_device_info = (
            build_thing_device_info(host, thing)
            if isinstance(thing, dict)
            else build_device_info(host, device_name)
        )
        item = (self.coordinator.data or {}).get(item_name)
        channel_metadata = (
            getattr(self.coordinator, "item_to_channel_metadata", {}) or {}
        ).get(item_name)

        self._attr_name = self._build_display_name()

        if item:
            meta = guess_ha_meta(
                getattr(item, "oh_type", None),
                getattr(item, "parsed", None),
                item_name,
                channel_metadata,
            )
            self._attr_device_class = meta.get("device_class")
            self._attr_state_class = meta.get("state_class")
            self._attr_native_unit_of_measurement = meta.get("suggested_unit")
            self._attr_icon = meta.get("icon")
            self._is_energy = (
                self._attr_device_class == SensorDeviceClass.ENERGY
                or self._attr_state_class == SensorStateClass.TOTAL_INCREASING
            )

    def _build_display_name(self) -> str:
        clean_item_name = normalize_item_name(
            self._item_name or "",
            getattr(self.coordinator, "multi_instance_device_types", set()),
        )
        base_name = clean_item_name.replace("harmonized_", "").replace("_", " ").strip()
        display_name = format_display_name(base_name)
        return f"{self._prefix} {display_name}".strip() if self._prefix else display_name

    def _sync_display_name(self) -> bool:
        new_name = self._build_display_name()
        if new_name == self._attr_name:
            return False
        self._attr_name = new_name
        return True

    def _is_invalid_energy_value(self, value) -> bool:
        if value is None or isinstance(value, bool):
            return True
        try:
            return not math.isfinite(float(value))
        except (TypeError, ValueError):
            return True

    def _should_write_energy(self, value) -> bool:
        if not self._is_energy:
            return True
        if self._is_invalid_energy_value(value):
            # Keep last valid energy value instead of overwriting with NULL/unavailable.
            return False
        new_val = float(value)
        if (
            self._energy_delta_kwh <= 0
            or self._last_energy_value is None
            or new_val < self._last_energy_value
            or (new_val - self._last_energy_value) >= self._energy_delta_kwh
        ):
            self._last_energy_value = new_val
            return True
        return False

    def _sync_energy_value(self, value) -> None:
        if not self._is_energy:
            return
        if self._is_invalid_energy_value(value):
            return
        new_val = float(value)
        self._last_energy_value = new_val if math.isfinite(new_val) else None

    def _handle_coordinator_update(self) -> None:
        name_changed = self._sync_display_name()
        update_success = getattr(self.coordinator, "last_update_success", None)
        if update_success != self._last_update_success:
            self._last_update_success = update_success
            self._sync_energy_value(self.native_value)
            super()._handle_coordinator_update()
            return
        if self._is_energy and not name_changed and not self._should_write_energy(self.native_value):
            return
        super()._handle_coordinator_update()

    @property
    def native_value(self):
        item = (self.coordinator.data or {}).get(self._item_name)
        if not item:
            return None
        val = item.parsed.value
        if self._is_energy and self._is_invalid_energy_value(val):
            return self._last_energy_value
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
    ):
        super().__init__(coordinator)
        self._thing_uid = thing_uid
        self._attr_unique_id = f"{entry_id}_thing_{thing_uid}"

        label = get_thing_display_name(thing, thing_uid)
        self._attr_name = label or thing_uid

        host = getattr(getattr(self.coordinator, "client", None), "host", None) or entry_id
        self._attr_device_info = build_thing_device_info(host, thing)

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
