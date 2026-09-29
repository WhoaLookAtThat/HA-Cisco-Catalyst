"""Config flow for Cisco Catalyst."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_CREDENTIAL_ACCESS,
    CONF_READ_COMMUNITY,
    CONF_SCAN_INTERVAL,
    CONF_SNMP_VERSION,
    CONF_SNMP_USERNAME,
    CONF_SNMP_AUTH_KEY,
    CONF_SNMP_PRIV_KEY,
    CONF_SNMP_AUTH_PROTOCOL,
    CONF_SNMP_PRIV_PROTOCOL,
    CONF_SNMP_PORT,
    CONF_WRITE_COMMUNITY,
    CONF_TRAP_ENABLED,
    CONF_TRAP_PORT,
    CREDENTIAL_ACCESS_READ_ONLY,
    CREDENTIAL_ACCESS_READ_WRITE,
    DEFAULT_CREDENTIAL_ACCESS,
    DEFAULT_READ_COMMUNITY,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_SNMP_PORT,
    DEFAULT_SNMP_VERSION,
    DEFAULT_SNMP_AUTH_PROTOCOL,
    DEFAULT_SNMP_PRIV_PROTOCOL,
    DEFAULT_WRITE_COMMUNITY,
    DEFAULT_TRAP_PORT,
    DOMAIN,
    MAX_SCAN_INTERVAL_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
    SYS_NAME,
)
from .snmp import CatalystSnmpClient, CatalystSnmpError


def _connection_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the shared SNMP connection schema."""
    values = defaults or {}
    access_default = values.get(
        CONF_CREDENTIAL_ACCESS,
        CREDENTIAL_ACCESS_READ_WRITE if defaults is not None else DEFAULT_CREDENTIAL_ACCESS,
    )
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=values.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_CREDENTIAL_ACCESS,
                default=access_default,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=CREDENTIAL_ACCESS_READ_ONLY,
                            label="Read-only",
                        ),
                        selector.SelectOptionDict(
                            value=CREDENTIAL_ACCESS_READ_WRITE,
                            label="Read/write",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_SNMP_VERSION,
                default=values.get(CONF_SNMP_VERSION, DEFAULT_SNMP_VERSION),
            ): vol.In(["2c", "3"]),
            vol.Optional(
                CONF_SNMP_PORT,
                default=values.get(CONF_SNMP_PORT, DEFAULT_SNMP_PORT),
            ): vol.All(int, vol.Range(min=1, max=65535)),
            vol.Optional(
                CONF_READ_COMMUNITY,
                description={
                    "suggested_value": values.get(
                        CONF_READ_COMMUNITY, DEFAULT_READ_COMMUNITY
                    )
                },
            ): str,
            vol.Optional(
                CONF_WRITE_COMMUNITY,
                description={
                    "suggested_value": values.get(
                        CONF_WRITE_COMMUNITY, DEFAULT_WRITE_COMMUNITY
                    )
                },
            ): str,
            vol.Optional(
                CONF_SNMP_USERNAME,
                description={
                    "suggested_value": values.get(CONF_SNMP_USERNAME, "")
                },
            ): str,
            vol.Optional(
                CONF_SNMP_AUTH_PROTOCOL,
                default=values.get(CONF_SNMP_AUTH_PROTOCOL, DEFAULT_SNMP_AUTH_PROTOCOL),
            ): vol.In(["sha", "sha256"]),
            vol.Optional(
                CONF_SNMP_AUTH_KEY,
                description={
                    "suggested_value": values.get(CONF_SNMP_AUTH_KEY, "")
                },
            ): str,
            vol.Optional(
                CONF_SNMP_PRIV_PROTOCOL,
                default=values.get(CONF_SNMP_PRIV_PROTOCOL, DEFAULT_SNMP_PRIV_PROTOCOL),
            ): vol.In(["aes128"]),
            vol.Optional(
                CONF_SNMP_PRIV_KEY,
                description={
                    "suggested_value": values.get(CONF_SNMP_PRIV_KEY, "")
                },
            ): str,
        }
    )


def _configuration_error(user_input: dict[str, Any]) -> tuple[str, str] | None:
    """Return the field and error key for incomplete active credentials."""
    version = user_input.get(CONF_SNMP_VERSION, DEFAULT_SNMP_VERSION)
    if version == "2c":
        if not user_input.get(CONF_READ_COMMUNITY, "").strip():
            return CONF_READ_COMMUNITY, "read_community_required"
        if (
            user_input.get(CONF_CREDENTIAL_ACCESS, DEFAULT_CREDENTIAL_ACCESS)
            == CREDENTIAL_ACCESS_READ_WRITE
            and not user_input.get(CONF_WRITE_COMMUNITY, "").strip()
        ):
            return CONF_WRITE_COMMUNITY, "write_community_required"
        return None

    if not user_input.get(CONF_SNMP_USERNAME, "").strip():
        return CONF_SNMP_USERNAME, "username_required"
    if not user_input.get(CONF_SNMP_AUTH_KEY, "").strip():
        return CONF_SNMP_AUTH_KEY, "auth_key_required"
    if not user_input.get(CONF_SNMP_PRIV_KEY, "").strip():
        return CONF_SNMP_PRIV_KEY, "priv_key_required"
    return None


def _sanitize_credentials(user_input: dict[str, Any]) -> dict[str, Any]:
    """Clear credentials that are inactive for the selected mode."""
    data = dict(user_input)
    version = data.get(CONF_SNMP_VERSION, DEFAULT_SNMP_VERSION)
    if version == "2c":
        if (
            data.get(CONF_CREDENTIAL_ACCESS, DEFAULT_CREDENTIAL_ACCESS)
            == CREDENTIAL_ACCESS_READ_ONLY
        ):
            data[CONF_WRITE_COMMUNITY] = ""
        data[CONF_SNMP_USERNAME] = ""
        data[CONF_SNMP_AUTH_KEY] = ""
        data[CONF_SNMP_PRIV_KEY] = ""
    else:
        data[CONF_READ_COMMUNITY] = ""
        data[CONF_WRITE_COMMUNITY] = ""
    return data


async def _validate_connection(hass: HomeAssistant, user_input: dict[str, Any]) -> str:
    """Validate SNMP settings and return sysName."""
    version = user_input.get(CONF_SNMP_VERSION, DEFAULT_SNMP_VERSION)
    if version == "3" and (
        not user_input.get(CONF_SNMP_USERNAME)
        or not user_input.get(CONF_SNMP_AUTH_KEY)
        or not user_input.get(CONF_SNMP_PRIV_KEY)
    ):
        raise CatalystSnmpError(
            "SNMPv3 requires username, authentication key, and privacy key"
        )
    client = CatalystSnmpClient(
        user_input[CONF_HOST],
        user_input[CONF_SNMP_PORT],
        user_input.get(CONF_READ_COMMUNITY, ""),
        user_input.get(CONF_WRITE_COMMUNITY, ""),
        version=version,
        username=user_input.get(CONF_SNMP_USERNAME, ""),
        auth_key=user_input.get(CONF_SNMP_AUTH_KEY, ""),
        priv_key=user_input.get(CONF_SNMP_PRIV_KEY, ""),
        auth_protocol=user_input.get(
            CONF_SNMP_AUTH_PROTOCOL, DEFAULT_SNMP_AUTH_PROTOCOL
        ),
        priv_protocol=user_input.get(
            CONF_SNMP_PRIV_PROTOCOL, DEFAULT_SNMP_PRIV_PROTOCOL
        ),
    )
    await client.async_initialize(hass)
    try:
        return (await client.get(SYS_NAME)).prettyPrint()
    finally:
        client.close()


class CatalystConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cisco Catalyst."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> CatalystOptionsFlow:
        """Return the options flow handler."""
        return CatalystOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()
            data = user_input | {CONF_HOST: host}
            if error := _configuration_error(data):
                field, error_key = error
                errors[field] = error_key
                errors["base"] = error_key
            else:
                data = _sanitize_credentials(data)
                try:
                    sys_name = await _validate_connection(
                        self.hass, data
                    )
                except (CatalystSnmpError, OSError, TimeoutError):
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=sys_name or host, data=data
                    )

        return self.async_show_form(
            step_id="user", data_schema=_connection_schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure SNMP transport and credentials without replacing the entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            data = user_input | {CONF_HOST: host}
            if error := _configuration_error(data):
                field, error_key = error
                errors[field] = error_key
                errors["base"] = error_key
            else:
                data = _sanitize_credentials(data)
                try:
                    await _validate_connection(self.hass, data)
                except (CatalystSnmpError, OSError, TimeoutError):
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(host.lower())
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=data,
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(dict(entry.data)),
            errors=errors,
        )


class CatalystOptionsFlow(OptionsFlowWithReload):
    """Handle Cisco Catalyst integration options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_SCAN_INTERVAL_SECONDS,
                        max=MAX_SCAN_INTERVAL_SECONDS,
                    ),
                ),
                vol.Required(
                    CONF_TRAP_ENABLED,
                    default=self.config_entry.options.get(CONF_TRAP_ENABLED, False),
                ): bool,
                vol.Required(
                    CONF_TRAP_PORT,
                    default=self.config_entry.options.get(CONF_TRAP_PORT, DEFAULT_TRAP_PORT),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
