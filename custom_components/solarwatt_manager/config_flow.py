from __future__ import annotations

import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_ITEM_NAMES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    CONF_NAME_PREFIX,
    DEFAULT_NAME_PREFIX,
)
from .coordinator import (
    SOLARWATTClient,
    SolarwattAuthError,
    SolarwattConnectionError,
    SolarwattNotManagerError,
    SolarwattProtocolError,
)

_LOGGER = logging.getLogger(__name__)


class SOLARWATTItemsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            # Validate input
            errors = self._validate_input(user_input)
            if not errors:
                # Test connection before creating entry
                errors = await self._test_connection(user_input, errors)
            
            if not errors:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"SOLARWATT ({user_input[CONF_HOST]})",
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options={
                        CONF_ITEM_NAMES: user_input.get(CONF_ITEM_NAMES, ""),
                        CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                        CONF_NAME_PREFIX: user_input.get(CONF_NAME_PREFIX, DEFAULT_NAME_PREFIX),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_USERNAME, default="installer"): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_ITEM_NAMES, default=""): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.Coerce(int),
                vol.Optional(CONF_NAME_PREFIX, default=""): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    def _validate_input(self, user_input: dict) -> dict:
        """Validate host, username, password, and scan interval."""
        errors = {}
        
        # Validate host
        host = (user_input.get(CONF_HOST) or "").strip()
        if not host:
            errors["base"] = "invalid_host"

        # Validate username
        username = (user_input.get(CONF_USERNAME) or "").strip()
        if not username:
            errors["base"] = "invalid_username"

        # Validate password
        password = (user_input.get(CONF_PASSWORD) or "").strip()
        if not password:
            errors["base"] = "invalid_password"
        
        # Validate scan interval
        try:
            scan = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            if scan < MIN_SCAN_INTERVAL or scan > MAX_SCAN_INTERVAL:
                errors["base"] = "invalid_scan_interval"
        except (ValueError, TypeError):
            errors["base"] = "invalid_scan_interval"
        
        return errors

    async def _test_connection(self, user_input: dict, errors: dict) -> dict:
        """Test connection to SOLARWATT Manager.
        
        Args:
            user_input: User input with host, username, password
            errors: Existing errors dictionary
        
        Returns:
            Updated errors dictionary with connection errors if any
        """
        if errors:
            # Don't test connection if input validation already failed
            return errors
        
        try:
            host = user_input.get(CONF_HOST, "").strip()
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "").strip()
            
            client = SOLARWATTClient(self.hass, host=host, username=username, password=password)
            try:
                await client.async_probe_manager()
                await client.async_validate_connection()
            finally:
                await client.async_close()
        except ValueError as e:
            # Invalid input (empty strings, etc.)
            _LOGGER.error(f"Invalid input for SOLARWATT Manager: {str(e)}")
            errors["base"] = "invalid_input"
        except SolarwattNotManagerError as e:
            _LOGGER.error(f"Host is not a SOLARWATT Manager: {str(e)}")
            errors["base"] = "not_solarwatt"
        except SolarwattAuthError as e:
            _LOGGER.error(f"Invalid SOLARWATT credentials: {str(e)}")
            errors["base"] = "invalid_auth"
        except SolarwattConnectionError as e:
            _LOGGER.error(f"Connection error to SOLARWATT Manager: {str(e)}")
            errors["base"] = "cannot_connect"
        except SolarwattProtocolError as e:
            _LOGGER.error(f"Unexpected SOLARWATT response: {str(e)}")
            errors["base"] = "connection_failed"
        except Exception as e:
            # Unexpected error
            _LOGGER.exception(f"Unexpected error testing SOLARWATT connection: {e}")
            errors["base"] = "unknown_error"
        
        return errors

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SOLARWATTItemsOptionsFlow(config_entry)


class SOLARWATTItemsOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        # Home Assistant exposes `config_entry` as a read-only property on
        # OptionsFlow (no setter). Store the entry in the internal attribute
        # expected by the base class so this works across HA versions.
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            # Validate input
            errors = self._validate_options_input(user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)
            
            # Re-show form with errors if validation failed
            return self.async_show_form(
                step_id="init", data_schema=self._build_options_schema(user_input), errors=errors
            )

        schema = self._build_options_schema()
        return self.async_show_form(step_id="init", data_schema=schema)

    def _build_options_schema(self, user_input=None) -> vol.Schema:
        """Build the options schema."""
        if user_input is None:
            user_input = self.config_entry.options
        
        return vol.Schema(
            {
                vol.Optional(
                    CONF_ITEM_NAMES,
                    default=user_input.get(CONF_ITEM_NAMES, ""),
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_NAME_PREFIX,
                    default=user_input.get(CONF_NAME_PREFIX, DEFAULT_NAME_PREFIX),
                ): str,
            }
        )

    def _validate_options_input(self, user_input: dict) -> dict:
        """Validate scan interval."""
        errors = {}
        
        # Validate scan interval
        try:
            scan = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            if scan < MIN_SCAN_INTERVAL or scan > MAX_SCAN_INTERVAL:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
        except (ValueError, TypeError):
            errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
        
        return errors
