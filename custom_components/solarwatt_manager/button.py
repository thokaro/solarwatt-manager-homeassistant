from __future__ import annotations

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


async def async_setup_entry(
    hass: HomeAssistant, entry: SOLARWATTConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    added_thing_uids: set[str] = set()
    selected_thing_uids = get_selected_thing_uids(entry.options)

    for thing_uid, thing in (getattr(coordinator, "things", {}) or {}).items():
        if selected_thing_uids is not None and thing_uid not in selected_thing_uids:
            continue
        added_thing_uids.add(thing_uid)
        entities.append(
            SOLARWATTDiagnosticsRefreshButton(
                coordinator,
                entry.entry_id,
                thing_uid,
                thing,
            )
        )

    if entities:
        async_add_entities(entities)

    @callback
    def _async_discover_new_entities() -> None:
        new_entities: list[ButtonEntity] = []
        for thing_uid, thing in (getattr(coordinator, "things", {}) or {}).items():
            if selected_thing_uids is not None and thing_uid not in selected_thing_uids:
                continue
            if thing_uid in added_thing_uids:
                continue
            added_thing_uids.add(thing_uid)
            new_entities.append(
                SOLARWATTDiagnosticsRefreshButton(
                    coordinator,
                    entry.entry_id,
                    thing_uid,
                    thing,
                )
            )
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.register_discovery_callback(_async_discover_new_entities))


class SOLARWATTDiagnosticsRefreshButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "diagnostics_refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, thing_uid: str, thing: dict):
        super().__init__(coordinator)
        self._thing_uid = thing_uid
        self._attr_unique_id = f"{entry_id}_thing_{thing_uid}_diagnostics_refresh"

        host = getattr(getattr(self.coordinator, "client", None), "host", None) or entry_id
        self._attr_device_info = build_thing_device_info(
            getattr(self.coordinator, "hass", None),
            host,
            thing,
            getattr(self.coordinator, "things", {}) or {},
        )

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_discovery_data()
