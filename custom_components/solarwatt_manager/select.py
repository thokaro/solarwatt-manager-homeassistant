from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    SOLARWATTConfigEntry,
    build_thing_device_info,
    get_selected_thing_uids,
)
from .entity_helpers import (
    build_thing_evstation_optimization_select_unique_id,
    is_hems_optimizable_thing,
)

OPTION_NOT_OPTIMIZED = "not_optimized"
OPTION_PV_OPTIMIZED = "pv_excess"
OPTION_DEPARTURE_TIME = "departure_time"

_OPTION_TO_MODE = {
    OPTION_NOT_OPTIMIZED: "NOT_OPTIMIZED",
    OPTION_PV_OPTIMIZED: "PV_EXCESS",
    OPTION_DEPARTURE_TIME: "DEPARTURE_TIME",
}
_MODE_TO_OPTION = {mode: option for option, mode in _OPTION_TO_MODE.items()}


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
        new_entities = _collect_hems_optimization_selects(
            coordinator,
            entry.entry_id,
            selected_thing_uids,
            added_thing_uids,
        )
        if new_entities:
            async_add_entities(new_entities)

    _async_discover_new_entities()
    entry.async_on_unload(coordinator.register_discovery_callback(_async_discover_new_entities))


def _collect_hems_optimization_selects(
    coordinator,
    entry_id: str,
    selected_thing_uids: set[str] | None,
    added_thing_uids: set[str],
) -> list[SelectEntity]:
    entities: list[SelectEntity] = []
    for thing_uid, thing in (coordinator.things or {}).items():
        if selected_thing_uids is not None and thing_uid not in selected_thing_uids:
            continue
        if thing_uid in added_thing_uids or not is_hems_optimizable_thing(thing):
            continue
        hems_device_id = _hems_device_id(thing, thing_uid)
        if not hems_device_id:
            continue
        added_thing_uids.add(thing_uid)
        entities.append(
            SOLARWATTHEMSOptimizationSelect(
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


def _current_option_from_thing(thing: Mapping[str, Any]) -> str | None:
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    for key in ("optimizationMode", "optimization_mode", "optimization.mode"):
        mode = str(props.get(key) or thing.get(key) or "").strip().upper()
        if option := _MODE_TO_OPTION.get(mode):
            return option
    return None


def _options_from_thing(thing: Mapping[str, Any]) -> list[str]:
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    modes = [
        str(mode or "").strip().upper()
        for mode in str(props.get("optimizationSupportedModes") or "").split(",")
        if str(mode or "").strip()
    ]
    options = [_MODE_TO_OPTION[mode] for mode in modes if mode in _MODE_TO_OPTION]
    return options or [OPTION_NOT_OPTIMIZED, OPTION_PV_OPTIMIZED]


class SOLARWATTHEMSOptimizationSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "evstation_optimization_mode"

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
        self._options = _options_from_thing(thing)
        self._current_option = _current_option_from_thing(thing)
        self._attr_unique_id = build_thing_evstation_optimization_select_unique_id(
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
    def options(self) -> list[str]:
        return self._options

    @property
    def current_option(self) -> str | None:
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        mode = _OPTION_TO_MODE.get(option)
        if mode is None:
            raise HomeAssistantError(f"Unsupported KiwiGrid HEMS optimization option: {option}")
        try:
            await self.coordinator.async_set_hems_device_optimization_mode(
                self._hems_device_id,
                mode,
            )
        except Exception as err:
            raise HomeAssistantError(
                f"Unable to set KiwiGrid HEMS optimization mode: {err}"
            ) from err
        self._current_option = option
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        thing = self.coordinator.things.get(self._thing_uid)
        if isinstance(thing, Mapping):
            self._options = _options_from_thing(thing)
            self._current_option = _current_option_from_thing(thing)
        super()._handle_coordinator_update()
