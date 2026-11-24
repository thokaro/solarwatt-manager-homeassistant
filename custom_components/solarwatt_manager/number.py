from __future__ import annotations

from math import isfinite, isclose
from functools import partial

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import SOLARWATTConfigEntry, build_thing_device_info, get_device_registry_anchor
from .entity_helpers import (
    build_thing_backup_state_of_charge_unique_id,
    build_thing_optimization_config_unique_id,
    is_hems_battery_thing,
    optimization_config_value,
    setup_hems_control_entities,
    supports_optimization_config,
)

DESCRIPTIONS = tuple(
    NumberEntityDescription(
        key=key,
        translation_key=key.replace(".", "_"),
        native_unit_of_measurement=unit,
        device_class=device_class,
        native_min_value=0,
        # Bound daily hours and percentages; other device limits are enforced by the API.
        native_max_value=(
            100 if unit == "%" else 24 if unit == "h" else
            2_147_483_647 / (1000 if unit == "kWh" else 1)
        ),
        native_step=0.001 if unit == "kWh" else 1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    )
    for key, unit, device_class in (
        ("lowest_power", "W", NumberDeviceClass.POWER),
        ("max_power", "W", NumberDeviceClass.POWER),
        ("min_runtime", "min", NumberDeviceClass.DURATION),
        ("min_resttime", "min", NumberDeviceClass.DURATION),
        ("must_runtime", "min", NumberDeviceClass.DURATION),
        ("target_time.capacity", "kWh", NumberDeviceClass.ENERGY),
        ("dynamic_tariff.capacity", "kWh", NumberDeviceClass.ENERGY),
        ("dynamic_tariff.operation_time", "h", NumberDeviceClass.DURATION),
        ("dynamic_tariff.target_state_of_charge", "%", NumberDeviceClass.BATTERY),
    )
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    for description in DESCRIPTIONS:
        setup_hems_control_entities(
            entry, async_add_entities,
            partial(supports_optimization_config, field=description.key),
            partial(
                SOLARWATTOptimizationNumber, entry.runtime_data, entry.entry_id,
                description=description,
            ),
        )
    setup_hems_control_entities(
        entry,
        async_add_entities,
        is_hems_battery_thing,
        lambda uid, thing, device_id, selected: SOLARWATTBackupStateOfChargeNumber(
            entry.runtime_data, entry.entry_id, uid, thing, device_id, selected,
        ),
    )


class SOLARWATTOptimizationNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator, entry_id: str, thing_uid: str, thing: dict,
        device_id: str, selected: set[str] | None, description: NumberEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._thing_uid = thing_uid
        self._hems_device_id = device_id
        self._attr_unique_id = build_thing_optimization_config_unique_id(entry_id, thing_uid, description.key)
        self._attr_device_info = build_thing_device_info(
            coordinator.hass, get_device_registry_anchor(coordinator.entry),
            thing, coordinator.things, selected, str(coordinator.client.host or ""),
            config_entry_id=entry_id,
        )

    @property
    def native_value(self) -> float | None:
        value = optimization_config_value(
            self.coordinator.things.get(self._thing_uid, {}), self.entity_description.key,
        )
        if value is None or not isfinite(value):
            return None
        return value / 1000 if self.entity_description.key in {"target_time.capacity", "dynamic_tariff.capacity"} else value

    @property
    def available(self) -> bool:
        thing = self.coordinator.things.get(self._thing_uid, {})
        if self.entity_description.key.startswith("dynamic_tariff."):
            if thing.get("properties", {}).get("optimizationMode") != "DYNAMIC_TARIFF":
                return False
        return super().available and supports_optimization_config(
            self.coordinator.things.get(self._thing_uid, {}), self.entity_description.key,
        ) and self.native_value is not None

    async def async_set_native_value(self, value: float) -> None:
        scale = 1000 if self.entity_description.key in {"target_time.capacity", "dynamic_tariff.capacity"} else 1
        if not self.entity_description.native_min_value <= value <= self.entity_description.native_max_value:
            raise HomeAssistantError("Optimization value is outside the allowed range")
        raw = value * scale
        if isinstance(value, bool) or not isfinite(raw) or raw < 0 or not isclose(raw, round(raw), rel_tol=0, abs_tol=1e-6):
            raise HomeAssistantError("Invalid optimization value")
        try:
            await self.coordinator.async_update_hems_device_optimization_config(
                self._hems_device_id, self.entity_description.key, round(raw),
            )
        except Exception as err:
            raise HomeAssistantError(f"Unable to update optimization setting: {err}") from err


class SOLARWATTBackupStateOfChargeNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "%"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "backup_state_of_charge"

    def __init__(self, coordinator, entry_id: str, thing_uid: str, thing: dict,
                 device_id: str, selected: set[str] | None) -> None:
        super().__init__(coordinator)
        self._thing_uid = thing_uid
        self._device_id = device_id
        self._attr_unique_id = build_thing_backup_state_of_charge_unique_id(entry_id, thing_uid)
        self._attr_device_info = build_thing_device_info(
            coordinator.hass, get_device_registry_anchor(coordinator.entry),
            thing, coordinator.things, selected, str(coordinator.client.host or ""),
            config_entry_id=entry_id,
        )

    def _current_value(self) -> float | None:
        for item_name, thing_uid in self.coordinator.item_to_thing_uid.items():
            if thing_uid != self._thing_uid or not item_name.endswith("_backup_state_of_charge"):
                continue
            item = (self.coordinator.data or {}).get(item_name)
            if item is None:
                continue
            try:
                raw_value = item.parsed.value
                if isinstance(raw_value, bool):
                    continue
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if isfinite(value):
                return value
        return None

    @property
    def native_value(self) -> float | None:
        pending = self.coordinator.hems_backup_state_of_charge.get(self._device_id)
        return pending if pending is not None else self._current_value()

    @property
    def available(self) -> bool:
        return super().available and self._current_value() is not None

    async def async_set_native_value(self, value: float) -> None:
        if isinstance(value, bool) or not isfinite(value) or not 0 <= value <= 100:
            raise HomeAssistantError("Backup state of charge must be between 0 and 100 percent")
        try:
            await self.coordinator.async_update_hems_battery_backup_state_of_charge(
                self._device_id,
                value,
                entity_id=getattr(self, "entity_id", None),
                entity_name=getattr(self, "name", None) or self._attr_translation_key,
            )
        except Exception as err:
            raise HomeAssistantError(f"Unable to update battery backup state of charge: {err}") from err
