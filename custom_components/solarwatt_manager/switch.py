from __future__ import annotations

from collections.abc import Mapping
import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    SOLARWATTConfigEntry,
    build_thing_device_info,
    get_selected_thing_uids,
    get_thing_display_name,
)
from .entity_helpers import (
    build_thing_optimization_switch_unique_id,
    is_hems_switchable_thing,
)
from .naming import slugify_entity_name

_PENDING_STATE_TTL = 30


async def async_setup_entry(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    added_thing_uids: set[str] = set()

    @callback
    def _async_discover_new_entities(options: Mapping[str, Any] | None = None) -> None:
        selected_thing_uids = get_selected_thing_uids(
            options if options is not None else entry.options
        )
        new_entities = _collect_hems_switches(
            coordinator,
            entry.entry_id,
            selected_thing_uids,
            added_thing_uids,
        )
        if new_entities:
            async_add_entities(new_entities)

    _async_discover_new_entities()
    entry.async_on_unload(coordinator.register_discovery_callback(_async_discover_new_entities))


def _collect_hems_switches(
    coordinator,
    entry_id: str,
    selected_thing_uids: set[str] | None,
    added_thing_uids: set[str],
) -> list[SwitchEntity]:
    entities: list[SwitchEntity] = []
    for thing_uid, thing in (coordinator.things or {}).items():
        if selected_thing_uids is not None and thing_uid not in selected_thing_uids:
            continue
        if thing_uid in added_thing_uids or not is_hems_switchable_thing(thing):
            continue
        hems_device_id = _hems_device_id(thing, thing_uid)
        if not hems_device_id:
            continue
        added_thing_uids.add(thing_uid)
        entities.append(
            SOLARWATTHEMSOptimizationSwitch(
                coordinator,
                entry_id,
                thing_uid,
                thing,
                hems_device_id,
                selected_thing_uids,
            )
        )
    return entities


def _hems_device_id(thing: Mapping[str, Any], fallback_uid: str) -> str:
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    return str(props.get("identifier") or fallback_uid or "").strip()


def _is_on_from_thing(thing: Mapping[str, Any]) -> bool | None:
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    state = str(props.get("optimizationSwitchState") or "").strip().upper()
    if state == "ON":
        return True
    if state == "OFF":
        return False
    return None


class SOLARWATTHEMSOptimizationSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator,
        entry_id: str,
        thing_uid: str,
        thing: dict,
        hems_device_id: str,
        selected_thing_uids: set[str] | None,
    ):
        super().__init__(coordinator)
        self._thing_uid = thing_uid
        self._hems_device_id = hems_device_id
        self._device_name = get_thing_display_name(thing, thing_uid)
        self._is_on = _is_on_from_thing(thing)
        self._pending_is_on: bool | None = None
        self._pending_until = 0.0
        self._attr_name = self._device_name
        self._attr_unique_id = build_thing_optimization_switch_unique_id(
            entry_id,
            thing_uid,
        )
        self._attr_device_info = build_thing_device_info(
            self.coordinator.hass,
            str(self.coordinator.client.host or entry_id),
            thing,
            self.coordinator.things,
            selected_thing_uids,
        )

    @property
    def is_on(self) -> bool | None:
        return self._is_on

    @property
    def suggested_object_id(self) -> str | None:
        device_slug = slugify_entity_name(self._device_name)
        return device_slug or None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set_state("ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_state("OFF")

    async def _async_set_state(self, target_state: str) -> None:
        target_is_on = target_state == "ON"
        self._pending_is_on = target_is_on
        self._pending_until = time.monotonic() + _PENDING_STATE_TTL
        self._is_on = target_is_on
        self.async_write_ha_state()
        try:
            await self.coordinator.async_set_hems_device_optimization_state(
                self._hems_device_id,
                target_state,
            )
        except Exception as err:
            self._pending_is_on = None
            self._pending_until = 0.0
            raise HomeAssistantError(
                f"Unable to switch KiwiGrid HEMS device {target_state}: {err}"
            ) from err
        self._is_on = target_is_on
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        thing = self.coordinator.things.get(self._thing_uid)
        if isinstance(thing, Mapping):
            hems_is_on = _is_on_from_thing(thing)
            if (
                self._pending_is_on is not None
                and time.monotonic() < self._pending_until
                and hems_is_on != self._pending_is_on
            ):
                self._is_on = self._pending_is_on
            else:
                self._pending_is_on = None
                self._pending_until = 0.0
                self._is_on = hems_is_on
        super()._handle_coordinator_update()
