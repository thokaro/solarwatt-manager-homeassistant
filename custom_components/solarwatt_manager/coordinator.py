from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import SOLARWATTClient, SolarwattAuthError, SolarwattError
from .const import (
    CONF_KIWIGRID_HEMS_ENABLED,
    CONF_KIWIGRID_HEMS_PASSWORD,
    CONF_KIWIGRID_HEMS_SCAN_INTERVAL,
    CONF_KIWIGRID_HEMS_USERNAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_KIWIGRID_HEMS_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .entity_helpers import detach_entityless_thing_devices, ensure_parent_devices_registered
from .hems_api import item_names_to_thing_uids
from .state_parser import SOLARWATTItem, parse_state
from .thing_matching import (
    canonicalize_thing_key as _canonicalize_item_reference,
    merge_thing_records as _merge_thing_records,
    resolve_thing_uid as _resolve_thing_uid,
)

if TYPE_CHECKING:
    from .stats_total import StatsTotalStore


class SOLARWATTCoordinator(DataUpdateCoordinator[dict[str, SOLARWATTItem]]):
    def __init__(self, hass: HomeAssistant, entry, client: SOLARWATTClient):
        self.entry = entry
        self.client = client
        self.stats_total_store: StatsTotalStore | None = None
        self.things: dict[str, dict[str, Any]] = {}
        self.item_to_thing_uid: dict[str, str] = {}
        self.item_to_channel_metadata: dict[str, dict[str, str]] = {}
        self.duplicate_item_targets: dict[str, str] = {}
        self._discovery_callbacks: set[Callable[[Mapping[str, Any] | None], None]] = set()
        self._local_items_cache: list[dict[str, Any]] = []
        self.local_last_error: str | None = None
        self._hems_items_cache: list[dict[str, Any]] = []
        self._hems_energy_flow_cache: list[dict[str, Any]] = []
        self._hems_items_error: SolarwattError | None = None
        self._hems_energy_flow_error: SolarwattError | None = None
        self._hems_last_attempt: float | None = None
        self._hems_energy_flow_retry_at: float | None = None
        self._hems_last_poll: float | None = None
        self.hems_last_success: float | None = None
        self.hems_last_error: str | None = None

        scan = _validated_scan_interval(
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            default=DEFAULT_SCAN_INTERVAL,
        )
        self._hems_scan_interval = _validated_scan_interval(
            entry.options.get(CONF_KIWIGRID_HEMS_SCAN_INTERVAL, DEFAULT_KIWIGRID_HEMS_SCAN_INTERVAL),
            default=DEFAULT_KIWIGRID_HEMS_SCAN_INTERVAL,
        )
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="solarwatt_items",
            update_interval=timedelta(seconds=int(scan)),
        )

    def register_discovery_callback(
        self,
        callback: Callable[[Mapping[str, Any] | None], None],
    ) -> Callable[[], None]:
        """Register a callback that discovers new entities on demand."""
        self._discovery_callbacks.add(callback)

        def _remove() -> None:
            self._discovery_callbacks.discard(callback)

        return _remove

    def run_discovery_callbacks(self, options: Mapping[str, Any] | None = None) -> None:
        """Run registered entity discovery callbacks."""
        for callback in tuple(self._discovery_callbacks):
            try:
                callback(options)
            except Exception:
                self.logger.exception("Error running discovery callback")

    async def async_refresh_discovery_data(self) -> None:
        """Refresh items/things and run one-shot entity discovery."""
        await self.async_refresh()
        await self.async_refresh_things()
        ensure_parent_devices_registered(self.hass, self.entry, self.things)
        self.run_discovery_callbacks()
        detach_entityless_thing_devices(self.hass, self.entry, self.things)

    async def _async_update_data(self) -> dict[str, SOLARWATTItem]:
        # Best practice for Home Assistant: do a single poll per update interval and
        # let all entities read from the same snapshot.
        items: list[dict[str, Any]] = []
        source_successes = 0
        source_errors: list[SolarwattError] = []

        if self._local_configured():
            local_items, local_success, local_errors = (
                await self._async_update_local_items()
            )
            items.extend(local_items)
            source_successes += int(local_success)
            source_errors.extend(local_errors)

        hems_enabled, hems_username, hems_password = self._hems_credentials()
        if hems_enabled:
            hems_items, hems_success, hems_errors = await self._async_update_hems_items(
                username=hems_username,
                password=hems_password,
            )
            items.extend(hems_items)
            source_successes += int(hems_success)
            source_errors.extend(hems_errors)
        else:
            self._reset_hems_update_state()

        self._handle_source_errors(items, source_successes, source_errors)

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

    async def _async_update_local_items(
        self,
    ) -> tuple[list[dict[str, Any]], bool, list[SolarwattError]]:
        """Update the local source and return its latest usable snapshot."""
        errors: list[SolarwattError] = []
        try:
            self._local_items_cache = list(await self.client.async_get_items())
        except SolarwattAuthError as err:
            errors.append(err)
            self._set_local_error(str(err))
        except SolarwattError as err:
            errors.append(err)
            self._set_local_error(str(err))
        except Exception as err:
            wrapped_error = SolarwattError(
                f"Unexpected error fetching local SOLARWATT data: {err}"
            )
            errors.append(wrapped_error)
            self._set_local_error(str(wrapped_error))
            self.logger.debug(
                "Unexpected error fetching local SOLARWATT data",
                exc_info=True,
            )
        else:
            self._set_local_error(None)
        return list(self._local_items_cache), not errors, errors

    async def _async_update_hems_items(
        self,
        *,
        username: str,
        password: str,
    ) -> tuple[list[dict[str, Any]], bool, list[SolarwattError]]:
        """Update HEMS sources and return their latest usable snapshots."""
        if not (username and password):
            auth_error = SolarwattAuthError(
                "KiwiGrid HEMS login credentials are not configured"
            )
            self._set_hems_error(str(auth_error))
            return [], False, [auth_error]

        hems_items, hems_items_error = await self._async_get_hems_items_for_update(
            username=username,
            password=password,
        )
        energy_flow_items, energy_flow_error = (
            await self._async_get_hems_energy_flow_items_for_update(
                username=username,
                password=password,
            )
        )
        errors = [
            error
            for error in (hems_items_error, energy_flow_error)
            if error is not None
        ]
        if errors:
            self._set_hems_error("; ".join(str(error) for error in errors))
        else:
            self.hems_last_success = time.time()
            self._set_hems_error(None)
        return (
            [*hems_items, *energy_flow_items],
            hems_items_error is None or energy_flow_error is None,
            errors,
        )

    def _reset_hems_update_state(self) -> None:
        """Clear HEMS cache and availability state when the source is disabled."""
        self._hems_items_cache = []
        self._hems_energy_flow_cache = []
        self._hems_items_error = None
        self._hems_energy_flow_error = None
        self._hems_last_attempt = None
        self._hems_energy_flow_retry_at = None
        self._hems_last_poll = None
        self.hems_last_success = None
        self.hems_last_error = None

    def _handle_source_errors(
        self,
        items: list[dict[str, Any]],
        source_successes: int,
        source_errors: list[SolarwattError],
    ) -> None:
        """Start reauthentication or fail when no configured source is usable."""
        auth_errors = [
            error
            for error in source_errors
            if isinstance(error, SolarwattAuthError)
        ]
        if auth_errors:
            if source_successes == 0 and not items:
                raise ConfigEntryAuthFailed(str(auth_errors[0])) from auth_errors[0]
            self._start_reauth()
        if source_successes == 0 and source_errors and not items:
            raise source_errors[0]

    async def _async_get_hems_items_for_update(
        self,
        *,
        username: str,
        password: str,
        include_energy_flow: bool = False,
    ) -> tuple[list[dict[str, Any]], SolarwattError | None]:
        now = time.monotonic()
        if (
            self._hems_last_attempt is not None
            and now - self._hems_last_attempt < self._hems_scan_interval
        ):
            return (
                _without_kiwigrid_flow_items(self._hems_items_cache),
                self._hems_items_error,
            )

        self._hems_last_attempt = now
        try:
            hems_items = await self.client.async_get_hems_items(
                username=username,
                password=password,
                include_energy_flow=include_energy_flow,
            )
            self._hems_items_cache = _without_kiwigrid_flow_items(hems_items or [])
            self._hems_last_poll = now
            partial_errors = tuple(
                getattr(self.client, "hems_partial_errors", ()) or ()
            )
            self._hems_items_error = (
                SolarwattError(
                    "Some KiwiGrid HEMS endpoints are unavailable: "
                    + "; ".join(partial_errors)
                )
                if partial_errors
                else None
            )
            if hems_items:
                self.logger.debug("Fetched %s KiwiGrid HEMS items", len(hems_items))
            else:
                self.logger.debug("KiwiGrid HEMS is enabled but returned no items")
        except SolarwattAuthError as err:
            self._hems_items_error = err
        except SolarwattError as err:
            self._hems_items_error = SolarwattError(
                f"Unable to fetch KiwiGrid HEMS data: {err}"
            )
        except Exception as err:
            self._hems_items_error = SolarwattError(
                f"Unexpected error fetching KiwiGrid HEMS data: {err}"
            )
            self.logger.debug(
                "Unexpected error fetching KiwiGrid HEMS data",
                exc_info=True,
            )
        return (
            _without_kiwigrid_flow_items(self._hems_items_cache),
            self._hems_items_error,
        )

    async def _async_get_hems_energy_flow_items_for_update(
        self,
        *,
        username: str,
        password: str,
    ) -> tuple[list[dict[str, Any]], SolarwattError | None]:
        now = time.monotonic()
        if (
            self._hems_energy_flow_retry_at is not None
            and now < self._hems_energy_flow_retry_at
        ):
            return list(self._hems_energy_flow_cache), self._hems_energy_flow_error

        try:
            energy_flow_items = await self.client.async_get_hems_energy_flow_items(
                username=username,
                password=password,
            )
            self._hems_energy_flow_cache = list(energy_flow_items or [])
            self._hems_energy_flow_error = None
            self._hems_energy_flow_retry_at = None
            if energy_flow_items:
                self.logger.debug(
                    "Fetched %s KiwiGrid HEMS energy flow items",
                    len(energy_flow_items),
                )
            return list(self._hems_energy_flow_cache), None
        except SolarwattAuthError as err:
            self._hems_energy_flow_error = err
        except SolarwattError as err:
            self._hems_energy_flow_error = SolarwattError(
                f"Unable to fetch KiwiGrid HEMS energy flow: {err}"
            )
        except Exception as err:
            self._hems_energy_flow_error = SolarwattError(
                f"Unexpected error fetching KiwiGrid HEMS energy flow: {err}"
            )
            self.logger.debug(
                "Unexpected error fetching KiwiGrid HEMS energy flow",
                exc_info=True,
            )
        self._hems_energy_flow_retry_at = now + self._hems_scan_interval
        return list(self._hems_energy_flow_cache), self._hems_energy_flow_error

    async def async_set_hems_device_optimization_mode(
        self,
        device_id: str,
        optimization_mode: str,
    ) -> None:
        """Set the optimization mode for one KiwiGrid HEMS device."""
        hems_enabled, hems_username, hems_password = self._hems_credentials()
        if not hems_enabled or not (hems_username and hems_password):
            raise SolarwattError("KiwiGrid HEMS is not configured")

        if optimization_mode not in {"PV_EXCESS", "NOT_OPTIMIZED", "DEPARTURE_TIME"}:
            raise SolarwattError(
                f"Unsupported KiwiGrid HEMS optimization mode: {optimization_mode}"
            )
        await self.client.async_set_hems_device_optimization_mode(
            device_id,
            optimization_mode,
            username=hems_username,
            password=hems_password,
        )
        self.invalidate_hems_cache()
        await self.async_refresh_things()
        if self._patch_hems_thing_property(
            device_id,
            "optimizationMode",
            optimization_mode,
        ):
            self.async_update_listeners()
        await self.async_request_refresh()

    async def async_set_hems_device_optimization_state(
        self,
        device_id: str,
        target_state: str,
    ) -> None:
        """Switch one KiwiGrid HEMS optimizable device on or off."""
        hems_enabled, hems_username, hems_password = self._hems_credentials()
        if not hems_enabled or not (hems_username and hems_password):
            raise SolarwattError("KiwiGrid HEMS is not configured")

        if target_state not in {"ON", "OFF"}:
            raise SolarwattError(f"Unsupported KiwiGrid HEMS switch state: {target_state}")
        await self.client.async_set_hems_device_optimization_state(
            device_id,
            target_state,
            username=hems_username,
            password=hems_password,
        )
        self.invalidate_hems_cache()
        await self.async_refresh_things()
        if self._patch_hems_thing_property(
            device_id,
            "optimizationSwitchState",
            target_state,
        ):
            self.async_update_listeners()
        await self.async_request_refresh()

    async def async_refresh_things(self, *, prefer_hems_cache: bool = False) -> None:
        if self._local_configured():
            try:
                things = await self.client.async_get_things()
            except SolarwattAuthError as err:
                self._start_reauth()
                self.logger.debug(
                    "Diagnostics: authentication failed fetching local thing metadata: %s",
                    err,
                )
                things = []
            except SolarwattError as err:
                self.logger.debug("Diagnostics: unable to fetch local thing metadata: %s", err)
                things = []
            except Exception as err:
                self.logger.debug(
                    "Diagnostics: unexpected error fetching local thing metadata: %s",
                    err,
                    exc_info=True,
                )
                things = []
        else:
            things = []

        hems_enabled, hems_username, hems_password = self._hems_credentials()
        if hems_enabled and hems_username and hems_password:
            try:
                hems_things = await self.client.async_get_hems_things(
                    username=hems_username,
                    password=hems_password,
                    include_energy_flow=True,
                    use_cached=prefer_hems_cache,
                )
                if hems_things:
                    self.logger.debug("Fetched %s KiwiGrid HEMS devices", len(hems_things))
                    things = list(things or []) + hems_things
            except SolarwattAuthError as err:
                self._start_reauth()
                self.logger.debug(
                    "Authentication failed fetching KiwiGrid HEMS devices: %s",
                    err,
                )
            except SolarwattError as err:
                self.logger.warning("Unable to fetch KiwiGrid HEMS devices: %s", err)
            except Exception as err:
                self.logger.warning(
                    "Unexpected error fetching KiwiGrid HEMS devices: %s",
                    err,
                    exc_info=True,
                )

        if not things:
            return

        out: dict[str, dict[str, Any]] = {}
        item_to_thing_uid: dict[str, str] = {}
        item_to_channel_metadata: dict[str, dict[str, str]] = {}
        duplicate_item_targets: dict[str, str] = {}
        kept_item_names: set[str] = set()
        for idx, thing in enumerate(things or []):
            raw_uid = str(thing.get("UID") or thing.get("uid") or f"unknown_{idx}").strip()
            uid = _resolve_thing_uid(out, thing, raw_uid)
            if uid != raw_uid:
                thing = dict(thing)
                thing["UID"] = uid
                thing["uid"] = uid
            if uid in out:
                thing = _merge_thing_records(out[uid], thing)
            out[uid] = thing
            for channel in thing.get("channels") or []:
                if not isinstance(channel, dict):
                    continue
                linked_items = channel.get("linkedItems")
                if not isinstance(linked_items, list):
                    continue
                kept_item_name = _find_kept_item_name(channel, linked_items)
                if kept_item_name:
                    kept_item_names.add(kept_item_name)
                channel_metadata = _channel_item_metadata(channel)
                for linked_item in linked_items:
                    if not linked_item:
                        continue
                    item_name = str(linked_item)
                    if item_name not in item_to_thing_uid:
                        item_to_thing_uid[item_name] = uid
                    if kept_item_name and item_name != kept_item_name:
                        duplicate_item_targets.setdefault(item_name, kept_item_name)
                    _merge_channel_item_metadata(
                        item_to_channel_metadata,
                        item_name,
                        channel_metadata,
                    )
        for item_name, thing_uid in item_names_to_thing_uids(
            tuple((self.data or {}).keys()),
            tuple(out.values()),
        ).items():
            item_to_thing_uid.setdefault(item_name, thing_uid)

        self.things = out
        self.item_to_thing_uid = item_to_thing_uid
        self.item_to_channel_metadata = item_to_channel_metadata
        self.duplicate_item_targets = {
            item_name: target
            for item_name, target in duplicate_item_targets.items()
            if item_name not in kept_item_names
        }

        self.async_update_listeners()

    def _hems_credentials(self) -> tuple[bool, str, str]:
        """Return enabled flag and normalized KiwiGrid HEMS credentials."""
        return (
            bool(self.entry.options.get(CONF_KIWIGRID_HEMS_ENABLED, False)),
            str(self.entry.options.get(CONF_KIWIGRID_HEMS_USERNAME, "") or "").strip(),
            str(self.entry.options.get(CONF_KIWIGRID_HEMS_PASSWORD, "") or "").strip(),
        )

    def _local_configured(self) -> bool:
        """Return True when the local SOLARWATT Manager connection is configured."""
        return bool(self.client.host and self.client.username and self.client.password)

    def invalidate_hems_cache(self) -> None:
        """Force the next refresh to fetch KiwiGrid HEMS data immediately."""
        self._hems_last_attempt = None
        self._hems_energy_flow_retry_at = None
        self._hems_last_poll = None

    def _set_local_error(self, error: str | None) -> None:
        """Log local source availability transitions without repeated warnings."""
        previous_error = self.local_last_error
        self.local_last_error = error
        if error and previous_error is None:
            self.logger.warning("Local SOLARWATT data became unavailable: %s", error)
        elif error and error != previous_error:
            self.logger.debug("Local SOLARWATT data remains unavailable: %s", error)
        elif error is None and previous_error is not None:
            self.logger.info("Local SOLARWATT data is available again")

    def _set_hems_error(self, error: str | None) -> None:
        """Log HEMS availability transitions without repeated warnings."""
        previous_error = self.hems_last_error
        self.hems_last_error = error
        if error and previous_error is None:
            self.logger.warning("KiwiGrid HEMS became unavailable: %s", error)
        elif error and error != previous_error:
            self.logger.debug("KiwiGrid HEMS remains unavailable: %s", error)
        elif error is None and previous_error is not None:
            self.logger.info("KiwiGrid HEMS is available again")

    def _start_reauth(self) -> None:
        """Start reauthentication while cached source data stays usable."""
        self.entry.async_start_reauth(self.hass)

    @property
    def hems_cache_age_seconds(self) -> int | None:
        """Return the age of the cached HEMS item snapshot."""
        if self._hems_last_poll is None:
            return None
        return max(0, int(time.monotonic() - self._hems_last_poll))

    async def async_calculate_hems_stats_total_value(
        self,
        item_name: str,
        *,
        max_years: int = 20,
        history_cache: dict[tuple[str, int], dict[str, Any]] | None = None,
    ) -> tuple[float, list[int]]:
        """Calculate a KiwiGrid stats offset from completed historic year values."""
        hems_enabled, hems_username, hems_password = self._hems_credentials()
        if not hems_enabled or not (hems_username and hems_password):
            raise SolarwattError("KiwiGrid HEMS is not configured")
        return await self.client.async_calculate_hems_stats_total_value(
            item_name,
            username=hems_username,
            password=hems_password,
            max_years=max_years,
            history_cache=history_cache,
        )

    def _patch_hems_thing_property(self, device_id: str, key: str, value: str) -> bool:
        """Patch freshly changed HEMS properties into thing metadata."""
        target_id = str(device_id or "").strip()
        if not target_id:
            return False

        for thing_uid, thing in tuple(self.things.items()):
            properties = thing.get("properties")
            props = properties if isinstance(properties, dict) else {}
            identifier = str(props.get("identifier") or thing_uid or "").strip()
            thing_id = str(thing.get("UID") or thing.get("uid") or "")
            if identifier != target_id and thing_id != target_id:
                continue
            patched = dict(thing)
            patched_props = dict(props)
            patched_props[key] = value
            patched["properties"] = patched_props
            self.things[thing_uid] = patched
            return True
        return False


def _validated_scan_interval(value: Any, *, default: int) -> int:
    if not isinstance(value, int) or value < MIN_SCAN_INTERVAL:
        return default
    return min(value, MAX_SCAN_INTERVAL)
def _find_kept_item_name(
    channel: dict[str, Any],
    linked_items: list[Any],
) -> str | None:
    """Return the UID-derived linked item that should represent one channel."""
    item_names = [
        str(linked_item).strip()
        for linked_item in linked_items
        if str(linked_item).strip()
    ]
    if not item_names:
        return None

    canonical_items = {
        _canonicalize_item_reference(item_name): item_name
        for item_name in item_names
    }

    for candidate in (channel.get("uid"), channel.get("UID")):
        canonical_candidate = _canonicalize_item_reference(candidate)
        if canonical_candidate and canonical_candidate in canonical_items:
            return canonical_items[canonical_candidate]

    canonical_channel_id = _canonicalize_item_reference(channel.get("id"))
    if canonical_channel_id:
        suffix_matches = [
            item_name
            for item_name in item_names
            if (
                canonical_item_name := _canonicalize_item_reference(item_name)
            ) == canonical_channel_id
            or canonical_item_name.endswith(f"_{canonical_channel_id}")
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0]

    return None


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


def _without_kiwigrid_flow_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return HEMS items without live KiwiGrid Flow values.

    KiwiGrid Flow values are fetched separately on every normal update. Keeping
    them out of the slower HEMS cache prevents stale energy-flow values from
    being reused when the live request fails.
    """
    return [
        item
        for item in items
        if str(item.get("category") or "").strip().lower() != "kiwigrid_flow"
    ]


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
