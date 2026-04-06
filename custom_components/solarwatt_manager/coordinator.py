from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import SOLARWATTClient, SolarwattError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .entity_helpers import detach_entityless_thing_devices, ensure_parent_devices_registered
from .state_parser import SOLARWATTItem, parse_state


class SOLARWATTCoordinator(DataUpdateCoordinator[dict[str, SOLARWATTItem]]):
    def __init__(self, hass: HomeAssistant, entry, client: SOLARWATTClient):
        self.entry = entry
        self.client = client
        self.things: dict[str, dict[str, Any]] = {}
        self.item_to_thing_uid: dict[str, str] = {}
        self.item_to_channel_metadata: dict[str, dict[str, str]] = {}
        self._discovery_callbacks: set[Callable[[], None]] = set()

        scan = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        # Validate scan interval: min MIN_SCAN_INTERVAL (10s), max MAX_SCAN_INTERVAL (1h)
        if not isinstance(scan, int) or scan < MIN_SCAN_INTERVAL:
            scan = DEFAULT_SCAN_INTERVAL
        if scan > MAX_SCAN_INTERVAL:
            scan = MAX_SCAN_INTERVAL
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="solarwatt_items",
            update_interval=timedelta(seconds=int(scan)),
        )

    def register_discovery_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback that discovers new entities on demand."""
        self._discovery_callbacks.add(callback)

        def _remove() -> None:
            self._discovery_callbacks.discard(callback)

        return _remove

    def _run_discovery_callbacks(self) -> None:
        for callback in tuple(self._discovery_callbacks):
            try:
                callback()
            except Exception:
                self.logger.exception("Error running discovery callback")

    async def async_refresh_discovery_data(self) -> None:
        """Refresh items/things and run one-shot entity discovery."""
        await self.async_refresh()
        await self.async_refresh_things()
        ensure_parent_devices_registered(self.hass, self.entry, self.things)
        self._run_discovery_callbacks()
        detach_entityless_thing_devices(self.hass, self.entry, self.things)

    async def _async_update_data(self) -> dict[str, SOLARWATTItem]:
        # Best practice for Home Assistant: do a single poll per update interval and
        # let all entities read from the same snapshot.
        items = await self.client.async_get_items()

        def _to_item(name: str, it: dict[str, Any]) -> SOLARWATTItem:
            pattern = (it.get("stateDescription") or {}).get("pattern")
            return SOLARWATTItem(
                name=name,
                raw=it,
                parsed=parse_state(it.get("state"), pattern, it.get("type")),
                oh_type=it.get("type"),
                editable=bool(it.get("editable")),
                label=it.get("label"),
                category=it.get("category"),
            )

        out_all: dict[str, SOLARWATTItem] = {}
        for idx, it in enumerate(items):
            n = it.get("name", f"unknown_{idx}")
            out_all[n] = _to_item(n, it)
        return out_all

    async def async_refresh_things(self) -> None:
        try:
            things = await self.client.async_get_things()
        except SolarwattError as err:
            self.logger.debug("Diagnostics: unable to fetch /rest/things: %s", err)
            return
        except Exception as err:
            self.logger.debug("Diagnostics: unexpected error fetching /rest/things: %s", err, exc_info=True)
            return

        out: dict[str, dict[str, Any]] = {}
        item_to_thing_uid: dict[str, str] = {}
        item_to_channel_metadata: dict[str, dict[str, str]] = {}
        for idx, thing in enumerate(things or []):
            uid = thing.get("UID") or thing.get("uid") or f"unknown_{idx}"
            out[uid] = thing
            for channel in thing.get("channels") or []:
                if not isinstance(channel, dict):
                    continue
                linked_items = channel.get("linkedItems")
                if not isinstance(linked_items, list):
                    continue
                channel_metadata = _channel_item_metadata(channel)
                for linked_item in linked_items:
                    if not linked_item:
                        continue
                    item_name = str(linked_item)
                    if item_name not in item_to_thing_uid:
                        item_to_thing_uid[item_name] = uid
                    _merge_channel_item_metadata(
                        item_to_channel_metadata,
                        item_name,
                        channel_metadata,
                    )
        self.things = out
        self.item_to_thing_uid = item_to_thing_uid
        self.item_to_channel_metadata = item_to_channel_metadata
        self.async_update_listeners()


def _channel_item_metadata(channel: dict[str, Any]) -> dict[str, str]:
    """Extract item-relevant metadata from a thing channel."""
    properties = channel.get("properties")
    props = properties if isinstance(properties, dict) else {}
    return {
        key: text
        for key, value in (
            ("channel_uid", channel.get("uid")),
            ("channel_type_uid", channel.get("channelTypeUID")),
            ("item_type", channel.get("itemType")),
            ("harmonized_item_type", props.get("kig.meta.harmonized.itemtype")),
            ("scope", props.get("kig.meta.scope")),
            ("channel_label", channel.get("label")),
        )
        if (text := str(value or "").strip())
    }


def _merge_channel_item_metadata(
    item_to_channel_metadata: dict[str, dict[str, str]],
    item_name: str,
    channel_metadata: dict[str, str],
) -> None:
    """Store channel metadata for one linked item, preferring richer typing."""
    if not channel_metadata:
        return

    existing = item_to_channel_metadata.get(item_name)
    if existing is None:
        item_to_channel_metadata[item_name] = dict(channel_metadata)
        return

    # Prefer metadata that provides a harmonized typed view, then fill gaps.
    if (
        "harmonized_item_type" in channel_metadata
        and "harmonized_item_type" not in existing
    ):
        existing.update(channel_metadata)
        return

    for key, value in channel_metadata.items():
        existing.setdefault(key, value)
