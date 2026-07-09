from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .stats_total_state import StatsTotalState, float_records, float_values

STORE_VERSION = 1


class StatsTotalStore:
    """Persist year-to-total rollover state and calibration offsets."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORE_VERSION,
            f"{DOMAIN}_stats_totals_{entry_id}",
        )
        self._state = StatsTotalState()

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self._state = StatsTotalState(
            sources=float_records(data.get("sources")),
            offsets=float_values(data.get("offsets")),
        )

    async def async_save(self) -> None:
        if not self._state.dirty:
            return
        self._state.dirty = False
        await self._store.async_save(
            {
                "sources": self._state.sources,
                "offsets": self._state.offsets,
            }
        )

    def calculated_value(self, source_key: str, year_value: Any) -> float | None:
        return self._state.calculated_value(source_key, year_value)

    def value_with_offset(self, source_key: str, year_value: Any) -> float | None:
        return self._state.value_with_offset(source_key, year_value)

    def offset(self, source_key: str) -> float:
        return self._state.offset(source_key)

    def set_offset(self, source_key: str, offset: Any) -> None:
        self._state.set_offset(source_key, offset)

    def set_desired_value(self, source_key: str, desired_value: Any, year_value: Any) -> float:
        return self._state.set_desired_value(source_key, desired_value, year_value)

    def reset_offset(self, source_key: str) -> None:
        self._state.reset_offset(source_key)

    @property
    def dirty(self) -> bool:
        return self._state.dirty
