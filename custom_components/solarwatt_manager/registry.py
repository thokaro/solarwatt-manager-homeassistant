"""Device registry compatibility for Home Assistant before and after 2026.8."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr


def get_device_by_identifier(
    registry: dr.DeviceRegistry,
    identifier: tuple[str, str],
    config_entry_id: str,
) -> dr.DeviceEntry | None:
    """Use entry-scoped lookups when available, otherwise the legacy registry."""
    if hasattr(registry, "async_get_device_by_identifier"):
        return registry.async_get_device_by_identifier(identifier, config_entry_id)
    return registry.async_get_device(identifiers={identifier})


def device_has_config_entry(device: dr.DeviceEntry, config_entry_id: str) -> bool:
    """Check device ownership without reading deprecated properties on new HA."""
    if hasattr(device, "config_entry_id"):
        return device.config_entry_id == config_entry_id
    return config_entry_id in device.config_entries


def remove_device_config_entry(
    registry: dr.DeviceRegistry,
    device: dr.DeviceEntry,
    config_entry_id: str,
) -> None:
    """Remove an owned device, preserving shared devices on older HA."""
    if not device_has_config_entry(device, config_entry_id):
        return
    if hasattr(registry, "async_get_device_by_identifier"):
        registry.async_remove_device(device.id)
    else:
        registry.async_update_device(
            device_id=device.id, remove_config_entry_id=config_entry_id
        )
