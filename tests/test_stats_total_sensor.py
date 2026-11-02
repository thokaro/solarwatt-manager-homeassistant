from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from .module_loader import load_component_module_with_stubs, make_homeassistant_stubs, make_module


@pytest.fixture
def modules():
    package = "solarwatt_stats_total_sensor_test"

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        async def async_added_to_hass(self):
            pass

        async def async_will_remove_from_hass(self):
            pass

        def async_entity_id_changed(self, old_entity_id):
            self.coordinator.renamed(old_entity_id)

    stubs = {
        **make_homeassistant_stubs(),
        "homeassistant.components.sensor": make_module(
            "homeassistant.components.sensor",
            SensorEntity=type("SensorEntity", (), {}),
            SensorEntityDescription=SimpleNamespace,
            SensorDeviceClass=SimpleNamespace(ENERGY="energy"),
            SensorStateClass=SimpleNamespace(MEASUREMENT="measurement", TOTAL_INCREASING="total_increasing"),
        ),
        "homeassistant.helpers.entity": make_module(
            "homeassistant.helpers.entity", EntityCategory=SimpleNamespace(DIAGNOSTIC="diagnostic")
        ),
        "homeassistant.helpers.entity_platform": make_module(
            "homeassistant.helpers.entity_platform", AddEntitiesCallback=object
        ),
        "homeassistant.helpers.update_coordinator": make_module(
            "homeassistant.helpers.update_coordinator", CoordinatorEntity=CoordinatorEntity
        ),
        "homeassistant.const": make_module("homeassistant.const", CONF_ENTITY_ID="entity_id"),
        "homeassistant.exceptions": make_module(
            "homeassistant.exceptions", HomeAssistantError=type("HomeAssistantError", (Exception,), {})
        ),
        "homeassistant.helpers.config_validation": make_module(
            "homeassistant.helpers.config_validation", entity_ids=lambda value: value
        ),
        f"{package}.client": make_module(
            f"{package}.client", SolarwattError=type("SolarwattError", (Exception,), {})
        ),
        f"{package}.sensor_meta": make_module(
            f"{package}.sensor_meta", guess_ha_meta=lambda *args: {}
        ),
        f"{package}.stats_total": make_module(f"{package}.stats_total", StatsTotalStore=object),
    }
    stubs["homeassistant.core"].ServiceCall = SimpleNamespace
    loaded = {}
    for name in ("const", "entity_helpers", "sensor", "services"):
        loaded[name] = load_component_module_with_stubs(name, package_name=package, stubs=stubs)
        stubs[f"{package}.{name}"] = loaded[name]
    return SimpleNamespace(**loaded, coordinator_class=CoordinatorEntity)


@pytest.mark.parametrize("in_place", [False, True], ids=["legacy", "in_place"])
def test_stats_services_follow_renames_and_cleanup(modules, in_place):
    if not in_place:
        # Older HA versions have no rename hook on the base class.
        del modules.coordinator_class.async_entity_id_changed

    registered = {}
    hass = SimpleNamespace(
        data={},
        services=SimpleNamespace(
            async_register=lambda domain, name, handler, **kwargs: registered.update({name: handler})
        ),
    )
    coordinator = SimpleNamespace(renamed=Mock())
    sensor = modules.sensor.SOLARWATTStatsTotalSensor(
        coordinator, "entry", "year_energy",
        source_entity=SimpleNamespace(
            name="Year Energy", device_info={}, native_unit_of_measurement="kWh", icon=None
        ),
        store=object(),
    )
    sensor.hass = hass
    sensor.entity_id = "sensor.original_total"
    sensor.set_offset = Mock()
    unique_id = sensor._attr_unique_id
    modules.services.async_register_services(hass)

    async def exercise_lifecycle():
        await sensor.async_added_to_hass()
        entities = hass.data[modules.const.DOMAIN][modules.sensor.STATS_TOTAL_ENTITY_MAP]
        for new_id in ("sensor.renamed_total", "sensor.renamed_again_total"):
            old_id = sensor.entity_id
            if in_place:
                sensor.entity_id = new_id
                sensor.async_entity_id_changed(old_id)
                coordinator.renamed.assert_called_with(old_id)
            else:
                await sensor.async_will_remove_from_hass()
                sensor.entity_id = new_id
                await sensor.async_added_to_hass()

            assert entities == {new_id: sensor}
            assert sensor._attr_unique_id == unique_id
            await registered["set_stats_value"](
                SimpleNamespace(data={"entity_id": [new_id], "offset": 12.5})
            )
            sensor.set_offset.assert_called_with(12.5)
            with pytest.raises(
                modules.services.HomeAssistantError, match="is not a SOLARWATT stats total sensor"
            ):
                await registered["set_stats_value"](
                    SimpleNamespace(data={"entity_id": [old_id], "offset": 99.0})
                )

        assert sensor.set_offset.call_count == 2
        await sensor.async_will_remove_from_hass()
        assert entities == {}
        with pytest.raises(
            modules.services.HomeAssistantError, match="No SOLARWATT stats total sensors"
        ):
            modules.services._all_stats_total_entities(hass)

    asyncio.run(exercise_lifecycle())
