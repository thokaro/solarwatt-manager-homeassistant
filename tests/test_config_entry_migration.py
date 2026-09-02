from __future__ import annotations

import asyncio
from types import SimpleNamespace

from .module_loader import load_component_module_with_stubs, make_module


PACKAGE_NAME = "solarwatt_manager_migration_test"


def _load_integration_module():
    def no_op(*args, **kwargs):
        return None

    return load_component_module_with_stubs(
        "__init__",
        package_name=PACKAGE_NAME,
        stubs={
            "homeassistant": make_module("homeassistant"),
            "homeassistant.core": make_module(
                "homeassistant.core",
                HomeAssistant=object,
            ),
            f"{PACKAGE_NAME}.client": make_module(
                f"{PACKAGE_NAME}.client",
                SOLARWATTClient=object,
            ),
            f"{PACKAGE_NAME}.const": make_module(
                f"{PACKAGE_NAME}.const",
                CONFIG_ENTRY_VERSION=3,
                SOLARWATTConfigEntry=object,
            ),
            f"{PACKAGE_NAME}.coordinator": make_module(
                f"{PACKAGE_NAME}.coordinator",
                SOLARWATTCoordinator=object,
            ),
            f"{PACKAGE_NAME}.entity_helpers": make_module(
                f"{PACKAGE_NAME}.entity_helpers",
                detach_entityless_thing_devices=no_op,
                ensure_parent_devices_registered=no_op,
                sync_selected_thing_entities=no_op,
            ),
            f"{PACKAGE_NAME}.registry_cleanup": make_module(
                f"{PACKAGE_NAME}.registry_cleanup",
                cleanup_empty_channel_thing_diagnostics=no_op,
            ),
            f"{PACKAGE_NAME}.registry_migrations": make_module(
                f"{PACKAGE_NAME}.registry_migrations",
                migrate_device_registry_identifiers=no_op,
            ),
            f"{PACKAGE_NAME}.services": make_module(
                f"{PACKAGE_NAME}.services",
                async_register_services=no_op,
            ),
            f"{PACKAGE_NAME}.stats_total": make_module(
                f"{PACKAGE_NAME}.stats_total",
                StatsTotalStore=object,
            ),
        },
    )


def test_migration_removes_obsolete_checkbox_options():
    integration = _load_integration_module()
    updates = []
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=lambda entry, **kwargs: updates.append(kwargs)
        )
    )
    entry = SimpleNamespace(
        version=2,
        options={
            "kiwigrid_hems_enabled": False,
            "disable_duplicate_item_entities": True,
            "kiwigrid_hems_username": "owner@example.com",
            "kiwigrid_hems_password": "secret",
            "scan_interval": 15,
        },
    )

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert updates == [
        {
            "options": {
                "kiwigrid_hems_username": "owner@example.com",
                "kiwigrid_hems_password": "secret",
                "scan_interval": 15,
            },
            "version": 3,
        }
    ]
