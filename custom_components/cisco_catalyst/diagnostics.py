"""Diagnostics support for Cisco Catalyst."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CREDENTIAL_ACCESS,
    CONF_SCAN_INTERVAL,
    CONF_SNMP_PORT,
    CONF_SNMP_VERSION,
    CONF_TRAP_ENABLED,
    CONF_TRAP_PORT,
    CREDENTIAL_ACCESS_READ_WRITE,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_SNMP_PORT,
    DEFAULT_SNMP_VERSION,
    DEFAULT_TRAP_PORT,
)
from .coordinator import CatalystCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry[CatalystCoordinator],
) -> dict[str, Any]:
    """Return non-secret configuration and the latest normalized SNMP snapshot."""
    coordinator = entry.runtime_data
    return {
        "config": {
            "host": "**REDACTED**",
            "snmp_port": entry.data.get(CONF_SNMP_PORT, DEFAULT_SNMP_PORT),
            "snmp_version": entry.data.get(CONF_SNMP_VERSION, DEFAULT_SNMP_VERSION),
            "credential_access": entry.data.get(
                CONF_CREDENTIAL_ACCESS, CREDENTIAL_ACCESS_READ_WRITE
            ),
            "trap_enabled": entry.options.get(CONF_TRAP_ENABLED, False),
            "trap_port": entry.options.get(CONF_TRAP_PORT, DEFAULT_TRAP_PORT),
            "scan_interval": entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
            ),
        },
        "last_update_success": coordinator.last_update_success,
        "data": asdict(coordinator.data),
    }
