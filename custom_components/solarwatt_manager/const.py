from __future__ import annotations

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
CONF_ENABLE_ALL_SENSORS = "enable_all_sensors"
CONF_ENERGY_DELTA_KWH = "energy_delta_kwh"

DEFAULT_SCAN_INTERVAL = 15  # Sekunden
MIN_SCAN_INTERVAL = 10  # Minimaler Scan-Interval in Sekunden
MAX_SCAN_INTERVAL = 3600  # Maximaler Scan-Interval in Sekunden (1 Stunde)

DEFAULT_NAME_PREFIX = ""
DEFAULT_ENABLE_ALL_SENSORS = False
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
