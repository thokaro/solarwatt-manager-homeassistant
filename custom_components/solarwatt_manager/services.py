from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .client import SolarwattError
from .const import DOMAIN
from .sensor import STATS_TOTAL_ENTITY_MAP, SOLARWATTStatsTotalSensor

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_STATS_VALUE = "set_stats_value"
SERVICE_RESET_STATS_VALUE = "reset_stats_value"
SERVICE_CALCULATE_STATS_VALUE = "calculate_stats_value"
SERVICE_CALCULATE_ALL_STATS_VALUES = "calculate_all_stats_values"

ATTR_VALUE = "value"
ATTR_OFFSET = "offset"
ATTR_MAX_YEARS = "max_years"

_TARGET_SCHEMA = vol.Schema({vol.Required(CONF_ENTITY_ID): cv.entity_ids})

SET_STATS_VALUE_SCHEMA = _TARGET_SCHEMA.extend(
    {
        vol.Optional(ATTR_VALUE): vol.Coerce(float),
        vol.Optional(ATTR_OFFSET): vol.Coerce(float),
    }
)
RESET_STATS_VALUE_SCHEMA = _TARGET_SCHEMA
_MAX_YEARS_SCHEMA = {
    vol.Optional(ATTR_MAX_YEARS, default=20): vol.All(
        vol.Coerce(int),
        vol.Range(min=1, max=100),
    ),
}
CALCULATE_STATS_VALUE_SCHEMA = _TARGET_SCHEMA.extend(_MAX_YEARS_SCHEMA)
CALCULATE_ALL_STATS_VALUES_SCHEMA = vol.Schema(
    {
        **_MAX_YEARS_SCHEMA,
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register SOLARWATT Manager entity services."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("services_registered"):
        return

    async def _async_set_stats_value(call: ServiceCall) -> None:
        has_value = ATTR_VALUE in call.data
        has_offset = ATTR_OFFSET in call.data
        if has_value == has_offset:
            raise HomeAssistantError("Set either value or offset")

        for entity in _stats_total_entities(hass, call.data):
            try:
                if has_offset:
                    entity.set_offset(call.data[ATTR_OFFSET])
                else:
                    entity.set_desired_value(call.data[ATTR_VALUE])
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err

    async def _async_reset_stats_value(call: ServiceCall) -> None:
        for entity in _stats_total_entities(hass, call.data):
            entity.reset_offset()

    async def _async_calculate_stats_value(call: ServiceCall) -> None:
        entities = _stats_total_entities(hass, call.data)
        max_years = call.data[ATTR_MAX_YEARS]
        hass.async_create_task(
            _async_calculate_stats_values(entities, max_years=max_years)
        )

    async def _async_calculate_all_stats_values(call: ServiceCall) -> None:
        entities = _all_stats_total_entities(hass)
        max_years = call.data[ATTR_MAX_YEARS]
        hass.async_create_task(
            _async_calculate_stats_values(entities, max_years=max_years)
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CALCULATE_ALL_STATS_VALUES,
        _async_calculate_all_stats_values,
        schema=CALCULATE_ALL_STATS_VALUES_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALCULATE_STATS_VALUE,
        _async_calculate_stats_value,
        schema=CALCULATE_STATS_VALUE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_STATS_VALUE,
        _async_set_stats_value,
        schema=SET_STATS_VALUE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_STATS_VALUE,
        _async_reset_stats_value,
        schema=RESET_STATS_VALUE_SCHEMA,
    )
    domain_data["services_registered"] = True


def _stats_total_entities(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> list[SOLARWATTStatsTotalSensor]:
    entities = hass.data.get(DOMAIN, {}).get(STATS_TOTAL_ENTITY_MAP, {})
    resolved: list[SOLARWATTStatsTotalSensor] = []
    for entity_id in data[CONF_ENTITY_ID]:
        entity = entities.get(entity_id)
        if not isinstance(entity, SOLARWATTStatsTotalSensor):
            raise HomeAssistantError(
                f"{entity_id} is not a SOLARWATT stats total sensor"
            )
        resolved.append(entity)
    return resolved


def _all_stats_total_entities(hass: HomeAssistant) -> list[SOLARWATTStatsTotalSensor]:
    entities = hass.data.get(DOMAIN, {}).get(STATS_TOTAL_ENTITY_MAP, {})
    resolved = [
        entity
        for entity in entities.values()
        if isinstance(entity, SOLARWATTStatsTotalSensor)
    ]
    if not resolved:
        raise HomeAssistantError("No SOLARWATT stats total sensors are registered")
    return sorted(resolved, key=lambda entity: entity.entity_id or "")


async def _async_calculate_stats_values(
    entities: list[SOLARWATTStatsTotalSensor],
    *,
    max_years: int,
) -> None:
    history_cache: dict[tuple[str, int], dict[str, Any]] = {}
    for entity in entities:
        try:
            offset, years = await entity.async_calculate_from_history(
                max_years=max_years,
                history_cache=history_cache,
            )
        except (SolarwattError, ValueError) as err:
            _LOGGER.warning(
                "Unable to calculate SOLARWATT stats total for %s: %s",
                entity.entity_id,
                err,
            )
            continue
        except Exception:
            _LOGGER.exception(
                "Unexpected error calculating SOLARWATT stats total for %s",
                entity.entity_id,
            )
            continue

        _LOGGER.info(
            "Calculated SOLARWATT stats offset for %s from completed years %s: %s",
            entity.entity_id,
            ", ".join(str(year) for year in years),
            offset,
        )
