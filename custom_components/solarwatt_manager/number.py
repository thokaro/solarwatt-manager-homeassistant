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
    build_thing_optimization_config_unique_id,
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
        # Technical integer limit only; device-specific limits are enforced by the API.
        native_max_value=2_147_483_647 / (1000 if unit == "kWh" else 1),
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
        return value / 1000 if self.entity_description.key == "target_time.capacity" else value

    @property
    def available(self) -> bool:
        return super().available and supports_optimization_config(
            self.coordinator.things.get(self._thing_uid, {}), self.entity_description.key,
        ) and self.native_value is not None

    async def async_set_native_value(self, value: float) -> None:
        scale = 1000 if self.entity_description.key == "target_time.capacity" else 1
        raw = value * scale
        if isinstance(value, bool) or not isfinite(raw) or raw < 0 or not isclose(raw, round(raw), rel_tol=0, abs_tol=1e-6):
            raise HomeAssistantError("Invalid optimization value")
        try:
            await self.coordinator.async_update_hems_device_optimization_config(
                self._hems_device_id, self.entity_description.key, round(raw),
            )
        except Exception as err:
            raise HomeAssistantError(f"Unable to update optimization setting: {err}") from err
