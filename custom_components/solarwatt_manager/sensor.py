from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENERGY_DELTA_KWH,
    CONF_POWER_UNAVAILABLE_THRESHOLD,
    DEFAULT_ENERGY_DELTA_KWH,
    DEFAULT_POWER_UNAVAILABLE_THRESHOLD,
    DOMAIN,
    SOLARWATTConfigEntry,
    build_device_info,
    build_thing_device_identifier,
    build_thing_device_info,
    get_disable_duplicate_item_entities,
    get_registry_device_name,
    get_selected_thing_uids,
    get_thing_display_name,
)
from .entity_helpers import (
    build_item_sensor_unique_id,
    build_stats_total_sensor_unique_id,
    build_thing_sensor_unique_id,
    collect_new_thing_entities,
    is_stats_total_source_item_name,
    iter_item_sensor_names,
)
from .naming import item_entity_name, slugify_entity_name, trim_device_tokens
from .sensor_meta import guess_ha_meta
from .stats_total import StatsTotalStore

STATS_TOTAL_ENTITY_MAP = "stats_total_entities"


async def async_setup_entry(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = entry.runtime_data
    energy_delta_kwh = float(entry.options.get(CONF_ENERGY_DELTA_KWH, DEFAULT_ENERGY_DELTA_KWH))
    power_unavailable_threshold = int(
        entry.options.get(
            CONF_POWER_UNAVAILABLE_THRESHOLD,
            DEFAULT_POWER_UNAVAILABLE_THRESHOLD,
        )
    )

    added_item_names: set[str] = set()
    added_stats_total_item_names: set[str] = set()
    added_thing_uids: set[str] = set()

    @callback
    def _async_discover_new_entities(options: Mapping[str, Any] | None = None) -> None:
        resolved_options = options if options is not None else entry.options
        selected_thing_uids = get_selected_thing_uids(resolved_options)
        if new_entities := _collect_new_entities(
            coordinator,
            entry,
            resolved_options,
            selected_thing_uids,
            energy_delta_kwh,
            power_unavailable_threshold,
            added_item_names,
            added_stats_total_item_names,
            added_thing_uids,
        ):
            async_add_entities(new_entities)

    _async_discover_new_entities()
    entry.async_on_unload(coordinator.register_discovery_callback(_async_discover_new_entities))


def _collect_new_entities(
    coordinator,
    entry: SOLARWATTConfigEntry,
    options: Mapping[str, Any],
    selected_thing_uids: set[str] | None,
    energy_delta_kwh: float,
    power_unavailable_threshold: int,
    added_item_names: set[str],
    added_stats_total_item_names: set[str],
    added_thing_uids: set[str],
) -> list[SensorEntity]:
    """Build newly discovered item and thing sensors that are not added yet."""
    entities: list[SensorEntity] = []
    disable_duplicate_item_entities = get_disable_duplicate_item_entities(options)
    for item_name in iter_item_sensor_names(
        coordinator.data,
        coordinator.item_to_thing_uid,
        selected_thing_uids,
    ):
        if item_name in added_item_names:
            continue

        added_item_names.add(item_name)
        enabled_default = not (
            disable_duplicate_item_entities
            and item_name in coordinator.duplicate_item_targets
        )
        entity = SOLARWATTItemSensor(
            coordinator,
            entry.entry_id,
            item_name,
            device_name=entry.title,
            energy_delta_kwh=energy_delta_kwh,
            power_unavailable_threshold=power_unavailable_threshold,
            enabled_default=enabled_default,
            selected_thing_uids=selected_thing_uids,
        )
        entities.append(entity)

        if (
            _is_stats_total_source(item_name, entity)
            and item_name not in added_stats_total_item_names
            and coordinator.stats_total_store is not None
        ):
            added_stats_total_item_names.add(item_name)
            entities.append(
                SOLARWATTStatsTotalSensor(
                    coordinator,
                    entry.entry_id,
                    item_name,
                    source_entity=entity,
                    store=coordinator.stats_total_store,
                )
            )

    entities.extend(
        collect_new_thing_entities(
            coordinator.things,
            selected_thing_uids,
            added_thing_uids,
            lambda thing_uid, thing: SOLARWATTThingSensor(
                coordinator,
                entry.entry_id,
                thing_uid,
                thing,
                selected_thing_uids,
            ),
        )
    )

    return entities


def _is_stats_total_source(item_name: str, source_entity: "SOLARWATTItemSensor") -> bool:
    """Return True for year-based KiwiGrid energy stats that can form totals."""
    return (
        is_stats_total_source_item_name(item_name)
        and source_entity.device_class == SensorDeviceClass.ENERGY
    )


class SOLARWATTItemSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator,
        entry_id: str,
        item_name: str,
        device_name: str = "SOLARWATT Manager",
        energy_delta_kwh: float = DEFAULT_ENERGY_DELTA_KWH,
        power_unavailable_threshold: int = DEFAULT_POWER_UNAVAILABLE_THRESHOLD,
        enabled_default: bool = True,
        selected_thing_uids: set[str] | None = None,
    ):
        super().__init__(coordinator)
        self._item_name = item_name
        self._default_device_name = device_name
        self._energy_delta_kwh = energy_delta_kwh
        self._power_unavailable_threshold = max(int(power_unavailable_threshold), 0)
        self._last_energy_value: float | None = None
        self._last_power_value: float | int | None = None
        self._consecutive_power_unavailable = 0
        self._last_update_success: bool | None = None
        self._is_energy = False
        self._is_total_increasing_energy = False
        self._is_power = False

        self._attr_unique_id = build_item_sensor_unique_id(entry_id, item_name)
        self._attr_entity_registry_enabled_default = enabled_default

        # Resolve the owning HA device once so naming and registry mapping stay aligned.
        things = self.coordinator.things
        self._host = str(self.coordinator.client.host or entry_id)
        self._thing_uid = self.coordinator.item_to_thing_uid.get(item_name)
        thing = things.get(self._thing_uid) if self._thing_uid else None
        self._attr_device_info = (
            build_thing_device_info(
                self.coordinator.hass,
                self._host,
                thing,
                things,
                selected_thing_uids,
            )
            if isinstance(thing, dict)
            else build_device_info(self._host, device_name)
        )
        item = (self.coordinator.data or {}).get(item_name)
        channel_metadata = self.coordinator.item_to_channel_metadata.get(item_name)

        self._attr_name = self._item_display_name()
        if item and item.raw.get("entityCategory") == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Cache sensor metadata once; update handling below only works with these flags.
        if item:
            meta = guess_ha_meta(
                item.oh_type,
                item.parsed,
                item_name,
                channel_metadata,
            )
            self._attr_device_class = meta.get("device_class")
            self._attr_state_class = meta.get("state_class")
            self._attr_native_unit_of_measurement = meta.get("suggested_unit")
            self._attr_icon = meta.get("icon")
            self._is_energy = self._attr_device_class == SensorDeviceClass.ENERGY
            self._is_total_increasing_energy = (
                self._attr_state_class in (SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING)
            )
            self._is_power = self._attr_device_class == SensorDeviceClass.POWER

    # Entity/device naming helpers.
    def _thing(self) -> dict | None:
        return self.coordinator.things.get(self._thing_uid)

    def _device_identifier(self) -> tuple[str, str]:
        if self._thing_uid:
            return build_thing_device_identifier(self._host, self._thing_uid)
        return DOMAIN, self._host

    def _build_device_name(self) -> str:
        registry_device_name = get_registry_device_name(self.hass, self._device_identifier())
        if registry_device_name:
            return registry_device_name

        thing = self._thing()
        if isinstance(thing, dict):
            return get_thing_display_name(thing, self._default_device_name)
        return self._default_device_name

    def _item_display_name(self) -> str:
        item = (self.coordinator.data or {}).get(self._item_name)
        if item:
            label = str(item.label or "").strip()
            if label:
                return label
        return item_entity_name(self._item_name)

    def _sync_display_name(self) -> bool:
        new_name = self._item_display_name()
        if new_name == self._attr_name:
            return False
        self._attr_name = new_name
        return True

    @property
    def suggested_object_id(self) -> str | None:
        device_name = self._build_device_name()
        sensor_name = self._item_display_name()
        return slugify_entity_name(trim_device_tokens(sensor_name, device_name)) or None

    # Numeric state handling for energy delta and temporary power unavailability.
    def _is_invalid_numeric_value(self, value) -> bool:
        if value is None or isinstance(value, bool):
            return True
        try:
            return not math.isfinite(float(value))
        except (TypeError, ValueError):
            return True

    def _sync_cached_numeric_values(self, value, *, update_energy: bool) -> None:
        is_invalid = self._is_invalid_numeric_value(value)
        if self._is_power and self._power_unavailable_threshold > 0:
            if is_invalid:
                self._consecutive_power_unavailable += 1
            else:
                self._last_power_value = value
                self._consecutive_power_unavailable = 0
        if update_energy and self._is_total_increasing_energy and not is_invalid:
            self._last_energy_value = float(value)

    def _should_write_energy(self, value) -> bool:
        if not self._is_total_increasing_energy:
            return True
        if self._is_invalid_numeric_value(value):
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

    def _current_item_value(self):
        item = (self.coordinator.data or {}).get(self._item_name)
        if not item:
            return None
        val = item.parsed.value
        if isinstance(val, str):
            return val.lstrip("#")
        return val

    # CoordinatorEntity hook: decide when state changes should reach Home Assistant.
    def _handle_coordinator_update(self) -> None:
        name_changed = self._sync_display_name()
        update_success = self.coordinator.last_update_success
        update_success_changed = update_success != self._last_update_success
        current_value = self._current_item_value()
        self._sync_cached_numeric_values(current_value, update_energy=update_success_changed)
        if update_success_changed:
            self._last_update_success = update_success
            super()._handle_coordinator_update()
            return
        if (
            self._is_total_increasing_energy
            and not name_changed
            and not self._should_write_energy(current_value)
        ):
            return
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return not (
            self._is_power
            and self._power_unavailable_threshold > 0
            and self._consecutive_power_unavailable >= self._power_unavailable_threshold
        )

    @property
    def native_value(self):
        val = self._current_item_value()
        if self._is_total_increasing_energy and self._is_invalid_numeric_value(val):
            return self._last_energy_value
        if self._is_power and self._is_invalid_numeric_value(val):
            if self._power_unavailable_threshold <= 0:
                return val
            if self._consecutive_power_unavailable < self._power_unavailable_threshold:
                return self._last_power_value
            return None
        return val


class SOLARWATTStatsTotalSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator,
        entry_id: str,
        item_name: str,
        *,
        source_entity: SOLARWATTItemSensor,
        store: StatsTotalStore,
    ) -> None:
        super().__init__(coordinator)
        self._item_name = item_name
        self._source_entity = source_entity
        self._store = store
        self._attr_unique_id = build_stats_total_sensor_unique_id(entry_id, item_name)
        self._attr_entity_registry_enabled_default = True
        self._attr_device_info = source_entity.device_info
        self._attr_native_unit_of_measurement = source_entity.native_unit_of_measurement
        self._attr_icon = source_entity.icon
        self._attr_name = ""
        self._last_value: float | None = None
        self._save_pending = False
        self._sync_display_name()

    @property
    def source_key(self) -> str:
        return self._item_name

    @property
    def offset(self) -> float:
        return self._store.offset(self._item_name)

    @property
    def suggested_object_id(self) -> str | None:
        device_name = self._source_entity._build_device_name()
        sensor_name = self._item_display_name()
        return slugify_entity_name(trim_device_tokens(sensor_name, device_name)) or None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.hass.data.setdefault(DOMAIN, {}).setdefault(STATS_TOTAL_ENTITY_MAP, {})[
            self.entity_id
        ] = self

    async def async_will_remove_from_hass(self) -> None:
        entities = self.hass.data.get(DOMAIN, {}).get(STATS_TOTAL_ENTITY_MAP, {})
        entities.pop(self.entity_id, None)
        await super().async_will_remove_from_hass()

    def _item_display_name(self) -> str:
        source_name = str(self._source_entity.name or item_entity_name(self._item_name)).strip()
        if source_name.lower().startswith("year "):
            source_name = source_name[5:].strip()
        return f"Total {source_name}"

    def _sync_display_name(self) -> bool:
        new_name = self._item_display_name()
        if new_name == self._attr_name:
            return False
        self._attr_name = new_name
        return True

    def _source_year_value(self):
        return self._source_entity.native_value

    def _calculate_native_value(self) -> float | None:
        value = self._store.value_with_offset(self._item_name, self._source_year_value())
        if value is not None and self._store.dirty:
            self._schedule_store_save()
        return value

    def _schedule_store_save(self) -> None:
        if self._save_pending:
            return
        self._save_pending = True

        async def _save() -> None:
            self._save_pending = False
            await self._store.async_save()

        self.hass.async_create_task(_save())

    def set_offset(self, offset: Any) -> None:
        self._store.set_offset(self._item_name, offset)
        self._schedule_store_save()
        self.async_write_ha_state()

    def set_desired_value(self, desired_value: Any) -> None:
        self._store.set_desired_value(
            self._item_name,
            desired_value,
            self._source_year_value(),
        )
        self._schedule_store_save()
        self.async_write_ha_state()

    def reset_offset(self) -> None:
        self._store.reset_offset(self._item_name)
        self._schedule_store_save()
        self.async_write_ha_state()

    async def async_calculate_from_history(
        self,
        *,
        max_years: int = 20,
        history_cache: dict[tuple[str, int], dict[str, Any]] | None = None,
    ) -> tuple[float, list[int]]:
        offset, years = await self.coordinator.async_calculate_hems_stats_total_value(
            self._item_name,
            max_years=max_years,
            history_cache=history_cache,
        )
        self._store.set_offset(self._item_name, offset)
        self._schedule_store_save()
        self.async_write_ha_state()
        return offset, years

    def _handle_coordinator_update(self) -> None:
        self._sync_display_name()
        value = self._calculate_native_value()
        if value == self._last_value:
            return
        self._last_value = value
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float | None:
        self._last_value = self._calculate_native_value()
        return self._last_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source_item": self._item_name,
            "offset": self.offset,
        }


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
        selected_thing_uids: set[str] | None,
    ):
        super().__init__(coordinator)
        self._thing_uid = thing_uid
        self._attr_unique_id = build_thing_sensor_unique_id(entry_id, thing_uid)

        self._attr_name = get_thing_display_name(thing, thing_uid) or thing_uid
        self._attr_device_info = build_thing_device_info(
            self.coordinator.hass,
            str(self.coordinator.client.host or entry_id),
            thing,
            self.coordinator.things,
            selected_thing_uids,
        )

    def _thing(self) -> dict | None:
        return self.coordinator.things.get(self._thing_uid)

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
