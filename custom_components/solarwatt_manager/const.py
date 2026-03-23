from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from typing import TYPE_CHECKING, TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

if TYPE_CHECKING:
    from .coordinator import SOLARWATTCoordinator

SOLARWATTConfigEntry: TypeAlias = ConfigEntry["SOLARWATTCoordinator"]

DOMAIN = "solarwatt_manager"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NAME_PREFIX = "name_prefix"
CONF_ENERGY_DELTA_KWH = "energy_delta_kwh"
CONF_ENABLED_THINGS = "enabled_things"

DEFAULT_SCAN_INTERVAL = 15  # Sekunden
MIN_SCAN_INTERVAL = 10  # Minimaler Scan-Interval in Sekunden
MAX_SCAN_INTERVAL = 3600  # Maximaler Scan-Interval in Sekunden (1 Stunde)

DEFAULT_NAME_PREFIX = ""
DEFAULT_ENERGY_DELTA_KWH = 0.01
MIN_ENERGY_DELTA_KWH = 0.0

DEVICE_MANUFACTURER = "SOLARWATT"
DEVICE_MODEL = "Manager flex / rail"


def build_device_info(host: str, device_name: str) -> DeviceInfo:
    """Build shared device metadata for all SOLARWATT entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, host)},
        name=device_name,
        manufacturer=DEVICE_MANUFACTURER,
        model=DEVICE_MODEL,
        configuration_url=f"http://{host}",
    )


def build_thing_device_identifier(host: str, thing_uid: str) -> tuple[str, str]:
    """Return the stable device-registry identifier for a SOLARWATT thing."""
    return DOMAIN, f"{host}:{thing_uid}"


def get_thing_display_name(thing: Mapping[str, Any], fallback: str = "") -> str:
    """Return the user-facing display name for a SOLARWATT thing."""
    label = str(thing.get("label") or fallback or "").strip()
    thing_type_uid = str(thing.get("thingTypeUID") or thing.get("thingTypeUid") or "").strip().lower()

    if (not label or label.lower() == "location") and "location" in thing_type_uid:
        return "KiwiGrid"
    return label or fallback


def get_thing_selection_detail(thing: Mapping[str, Any]) -> str:
    """Return a compact detail suffix for device selection labels."""
    properties = thing.get("properties")
    props = properties if isinstance(properties, Mapping) else {}

    generated_label = str(props.get("generatedLabel") or "").strip()

    if generated_label:
        return generated_label
    return str(thing.get("thingTypeUID") or thing.get("thingTypeUid") or "").strip()


def build_thing_device_info(host: str, thing: dict[str, Any]) -> DeviceInfo:
    """Build device metadata for a SOLARWATT thing node."""
    thing_uid = str(thing.get("UID") or thing.get("uid") or "").strip()
    label = get_thing_display_name(thing, thing_uid or host)
    properties = thing.get("properties")
    props = properties if isinstance(properties, dict) else {}
    selection_detail = get_thing_selection_detail(thing)

    manufacturer = (
        props.get("vendor")
        or props.get("manufacturer")
        or DEVICE_MANUFACTURER
    )
    model = (
        selection_detail
        or "Thing"
    )
    serial_number = (
        props.get("serialNumber")
        or props.get("serial")
        or props.get("identifier")
    )
    sw_version = props.get("firmwareVersion") or props.get("firmware")
    hw_version = props.get("hardwareVersion")

    bridge_uid = str(thing.get("bridgeUID") or thing.get("bridgeUid") or "").strip()
    via_device = build_thing_device_identifier(host, bridge_uid) if bridge_uid else None

    return DeviceInfo(
        identifiers={build_thing_device_identifier(host, thing_uid)},
        name=label,
        manufacturer=str(manufacturer).strip(),
        model=str(model).strip(),
        serial_number=str(serial_number).strip() if serial_number else None,
        sw_version=str(sw_version).strip() if sw_version else None,
        hw_version=str(hw_version).strip() if hw_version else None,
        via_device=via_device,
        configuration_url=f"http://{host}",
    )


def get_selected_thing_uids(options: Mapping[str, Any] | None) -> set[str] | None:
    """Return the configured selected thing UIDs, or None if all are enabled."""
    if not options or CONF_ENABLED_THINGS not in options:
        return None

    raw_values = options.get(CONF_ENABLED_THINGS)
    if raw_values is None:
        return None
    if isinstance(raw_values, str):
        values = [raw_values]
    elif isinstance(raw_values, (list, tuple, set)):
        values = raw_values
    else:
        values = []

    return {
        value
        for item in values
        if (value := str(item).strip())
    }
