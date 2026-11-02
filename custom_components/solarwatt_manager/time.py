from __future__ import annotations

from datetime import time
from math import isfinite

from homeassistant.components.time import TimeEntity, TimeEntityDescription
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

DESCRIPTION = TimeEntityDescription(
    key="target_time.target_time", translation_key="departure_time",
    entity_category=EntityCategory.CONFIG, icon="mdi:clock-outline",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    setup_hems_control_entities(
        entry, async_add_entities,
        lambda thing: supports_optimization_config(thing, DESCRIPTION.key),
        lambda uid, thing, device_id, selected: SOLARWATTDepartureTime(
            entry.runtime_data, entry.entry_id, uid, thing, device_id, selected,
        ),
    )


class SOLARWATTDepartureTime(CoordinatorEntity, TimeEntity):
    _attr_has_entity_name = True
    entity_description = DESCRIPTION

    def __init__(
        self, coordinator, entry_id: str, thing_uid: str, thing: dict,
        device_id: str, selected: set[str] | None,
    ) -> None:
        super().__init__(coordinator)
        self._thing_uid = thing_uid
        self._hems_device_id = device_id
        self._attr_unique_id = build_thing_optimization_config_unique_id(entry_id, thing_uid, DESCRIPTION.key)
        self._attr_device_info = build_thing_device_info(
            coordinator.hass, get_device_registry_anchor(coordinator.entry),
            thing, coordinator.things, selected, str(coordinator.client.host or ""),
            config_entry_id=entry_id,
        )

    @property
    def native_value(self) -> time | None:
        value = optimization_config_value(self.coordinator.things.get(self._thing_uid, {}), DESCRIPTION.key)
        if value is None or not isfinite(value) or not 0 <= value < 86_400_000 or value % 60_000:
            return None
        minutes = int(value) // 60_000
        return time(minutes // 60, minutes % 60)

    @property
    def available(self) -> bool:
        return super().available and supports_optimization_config(
            self.coordinator.things.get(self._thing_uid, {}), DESCRIPTION.key,
        ) and self.native_value is not None

    async def async_set_value(self, value: time) -> None:
        if value.tzinfo is not None or value.second or value.microsecond:
            raise HomeAssistantError("Departure time must be a local time with minute precision")
        try:
            await self.coordinator.async_update_hems_device_optimization_config(
                self._hems_device_id, DESCRIPTION.key, (value.hour * 60 + value.minute) * 60_000,
            )
        except Exception as err:
            raise HomeAssistantError(f"Unable to update departure time: {err}") from err
