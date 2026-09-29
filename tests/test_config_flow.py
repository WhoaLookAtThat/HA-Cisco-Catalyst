"""Tests for Cisco Catalyst config flow helpers."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_HOST

from custom_components.cisco_catalyst.config_flow import (
    _connection_schema,
    _validate_connection,
    _configuration_error,
    _sanitize_credentials,
)
from custom_components.cisco_catalyst.const import (
    CONF_CREDENTIAL_ACCESS,
    CONF_READ_COMMUNITY,
    CONF_SNMP_AUTH_KEY,
    CONF_SNMP_PORT,
    CONF_SNMP_PRIV_KEY,
    CONF_SNMP_USERNAME,
    CONF_SNMP_VERSION,
    CONF_WRITE_COMMUNITY,
    CREDENTIAL_ACCESS_READ_ONLY,
    CREDENTIAL_ACCESS_READ_WRITE,
)
from custom_components.cisco_catalyst.snmp import CatalystSnmpError


def test_connection_schema_accepts_explicit_host_for_initial_setup() -> None:
    result = _connection_schema()({CONF_HOST: "switch.example"})
    assert result[CONF_HOST] == "switch.example"
    assert result[CONF_CREDENTIAL_ACCESS] == CREDENTIAL_ACCESS_READ_ONLY


def test_connection_schema_preserves_reconfigure_defaults() -> None:
    result = _connection_schema(
        {
            CONF_HOST: "switch.example",
            CONF_CREDENTIAL_ACCESS: CREDENTIAL_ACCESS_READ_WRITE,
            CONF_SNMP_VERSION: "3",
            CONF_SNMP_PORT: 1161,
            CONF_READ_COMMUNITY: "",
            CONF_WRITE_COMMUNITY: "",
            CONF_SNMP_USERNAME: "ha-catalyst",
            CONF_SNMP_AUTH_KEY: "auth-secret",
            CONF_SNMP_PRIV_KEY: "priv-secret",
        }
    )({})
    assert result[CONF_HOST] == "switch.example"
    assert result[CONF_CREDENTIAL_ACCESS] == CREDENTIAL_ACCESS_READ_WRITE
    assert result[CONF_SNMP_VERSION] == "3"
    assert result[CONF_SNMP_PORT] == 1161
    # Credential fields use suggested_value rather than schema defaults so
    # inactive blank fields are not treated as required by the frontend.
    assert CONF_SNMP_USERNAME not in result


def test_reconfigure_legacy_entry_defaults_to_read_write() -> None:
    result = _connection_schema({CONF_HOST: "switch.example"})({})
    assert result[CONF_CREDENTIAL_ACCESS] == CREDENTIAL_ACCESS_READ_WRITE


def test_v2c_requires_read_community() -> None:
    assert _configuration_error(
        {
            CONF_CREDENTIAL_ACCESS: CREDENTIAL_ACCESS_READ_ONLY,
            CONF_SNMP_VERSION: "2c",
            CONF_READ_COMMUNITY: "",
            CONF_WRITE_COMMUNITY: "",
        }
    ) == (CONF_READ_COMMUNITY, "read_community_required")


def test_read_write_v2c_requires_write_community() -> None:
    assert _configuration_error(
        {
            CONF_CREDENTIAL_ACCESS: CREDENTIAL_ACCESS_READ_WRITE,
            CONF_SNMP_VERSION: "2c",
            CONF_READ_COMMUNITY: "public",
            CONF_WRITE_COMMUNITY: "",
        }
    ) == (CONF_WRITE_COMMUNITY, "write_community_required")


def test_read_only_v2c_clears_write_and_v3_credentials() -> None:
    sanitized = _sanitize_credentials(
        {
            CONF_CREDENTIAL_ACCESS: CREDENTIAL_ACCESS_READ_ONLY,
            CONF_SNMP_VERSION: "2c",
            CONF_READ_COMMUNITY: "public",
            CONF_WRITE_COMMUNITY: "private",
            CONF_SNMP_USERNAME: "ha",
            CONF_SNMP_AUTH_KEY: "auth",
            CONF_SNMP_PRIV_KEY: "priv",
        }
    )
    assert sanitized[CONF_WRITE_COMMUNITY] == ""
    assert sanitized[CONF_SNMP_USERNAME] == ""
    assert sanitized[CONF_SNMP_AUTH_KEY] == ""
    assert sanitized[CONF_SNMP_PRIV_KEY] == ""


def test_v3_clears_v2c_credentials() -> None:
    sanitized = _sanitize_credentials(
        {
            CONF_CREDENTIAL_ACCESS: CREDENTIAL_ACCESS_READ_WRITE,
            CONF_SNMP_VERSION: "3",
            CONF_READ_COMMUNITY: "public",
            CONF_WRITE_COMMUNITY: "private",
            CONF_SNMP_USERNAME: "ha",
            CONF_SNMP_AUTH_KEY: "auth",
            CONF_SNMP_PRIV_KEY: "priv",
        }
    )
    assert sanitized[CONF_READ_COMMUNITY] == ""
    assert sanitized[CONF_WRITE_COMMUNITY] == ""


@pytest.mark.asyncio
async def test_validate_connection_requires_complete_v3_authpriv() -> None:
    with pytest.raises(CatalystSnmpError, match="requires username"):
        await _validate_connection(
            object(),
            {
                CONF_HOST: "switch.example",
                CONF_SNMP_VERSION: "3",
                CONF_SNMP_PORT: 161,
                CONF_READ_COMMUNITY: "",
                CONF_WRITE_COMMUNITY: "",
                CONF_SNMP_USERNAME: "ha-catalyst",
                CONF_SNMP_AUTH_KEY: "",
                CONF_SNMP_PRIV_KEY: "",
            },
        )


def test_blank_inactive_credentials_are_not_schema_required() -> None:
    result = _connection_schema(
        {
            CONF_HOST: "switch.example",
            CONF_CREDENTIAL_ACCESS: CREDENTIAL_ACCESS_READ_WRITE,
            CONF_SNMP_VERSION: "2c",
            CONF_SNMP_PORT: 161,
            CONF_READ_COMMUNITY: "public",
            CONF_WRITE_COMMUNITY: "",
            CONF_SNMP_USERNAME: "",
            CONF_SNMP_AUTH_KEY: "",
            CONF_SNMP_PRIV_KEY: "",
        }
    )(
        {
            CONF_HOST: "switch.example",
            CONF_CREDENTIAL_ACCESS: CREDENTIAL_ACCESS_READ_WRITE,
            CONF_SNMP_VERSION: "2c",
            CONF_SNMP_PORT: 161,
            CONF_READ_COMMUNITY: "public",
            CONF_WRITE_COMMUNITY: "private",
        }
    )
    assert CONF_SNMP_USERNAME not in result
    assert CONF_SNMP_AUTH_KEY not in result
    assert CONF_SNMP_PRIV_KEY not in result


def test_v3_validation_identifies_each_missing_active_field() -> None:
    base = {
        CONF_CREDENTIAL_ACCESS: CREDENTIAL_ACCESS_READ_ONLY,
        CONF_SNMP_VERSION: "3",
        CONF_SNMP_USERNAME: "ha",
        CONF_SNMP_AUTH_KEY: "auth",
        CONF_SNMP_PRIV_KEY: "priv",
    }
    for field, error_key in (
        (CONF_SNMP_USERNAME, "username_required"),
        (CONF_SNMP_AUTH_KEY, "auth_key_required"),
        (CONF_SNMP_PRIV_KEY, "priv_key_required"),
    ):
        data = dict(base)
        data[field] = ""
        assert _configuration_error(data) == (field, error_key)
