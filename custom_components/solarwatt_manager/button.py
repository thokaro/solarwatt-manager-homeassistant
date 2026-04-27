from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    SOLARWATTConfigEntry,
    build_thing_device_info,
    get_selected_thing_uids,
)
from .entity_helpers import (
    build_thing_diagnostics_refresh_unique_id,
    collect_new_thing_entities,
)


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
        if new_entities := collect_new_thing_entities(
            coordinator.things,
            selected_thing_uids,
            added_thing_uids,
            lambda thing_uid, thing: SOLARWATTDiagnosticsRefreshButton(
                coordinator,
                entry.entry_id,
                thing_uid,
                thing,
                selected_thing_uids,
            ),
        ):
            async_add_entities(new_entities)

    _async_discover_new_entities()
    entry.async_on_unload(coordinator.register_discovery_callback(_async_discover_new_entities))


class SOLARWATTDiagnosticsRefreshButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "diagnostics_refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        self._attr_unique_id = build_thing_diagnostics_refresh_unique_id(entry_id, thing_uid)
        self._attr_device_info = build_thing_device_info(
            self.coordinator.hass,
            str(self.coordinator.client.host or entry_id),
            thing,
            self.coordinator.things,
            selected_thing_uids,
        )

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_discovery_data()
