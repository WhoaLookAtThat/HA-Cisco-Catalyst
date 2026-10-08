"""Cisco Catalyst integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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
    CREDENTIAL_ACCESS_READ_WRITE,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_SNMP_PORT,
    DEFAULT_SNMP_VERSION,
    DEFAULT_SNMP_AUTH_PROTOCOL,
    DEFAULT_SNMP_PRIV_PROTOCOL,
    DEFAULT_TRAP_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import CatalystCoordinator
from .mac_movement import MacMovementTracker
from .snmp import CatalystSnmpClient
from .trap import CatalystTrapReceiver

_LOGGER = logging.getLogger(__name__)

# Home Assistant imports the integration module in its import executor. Import
# entity platforms here so async_forward_entry_setups does not first import them
# on the event loop.
from . import binary_sensor as _binary_sensor  # noqa: F401, E402
from . import button as _button  # noqa: F401, E402
from . import sensor as _sensor  # noqa: F401, E402
from . import select as _select  # noqa: F401, E402
from . import switch as _switch  # noqa: F401, E402
from . import text as _text  # noqa: F401, E402


type CatalystConfigEntry = ConfigEntry[CatalystCoordinator]


def _remove_legacy_access_vlan_number_entities(
    hass: HomeAssistant, entry: CatalystConfigEntry
) -> None:
    """Remove stale number entities replaced by the access-VLAN select platform."""
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            entity.domain == "number"
            and entity.platform == DOMAIN
            and entity.unique_id.endswith("_access_vlan")
        ):
            registry.async_remove(entity.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: CatalystConfigEntry) -> bool:
    """Set up Cisco Catalyst from a config entry."""
    client = CatalystSnmpClient(
        entry.data[CONF_HOST],
        entry.data.get(CONF_SNMP_PORT, DEFAULT_SNMP_PORT),
        entry.data.get(CONF_READ_COMMUNITY, ""),
        entry.data.get(CONF_WRITE_COMMUNITY, ""),
        version=entry.data.get(CONF_SNMP_VERSION, DEFAULT_SNMP_VERSION),
        username=entry.data.get(CONF_SNMP_USERNAME, ""),
        auth_key=entry.data.get(CONF_SNMP_AUTH_KEY, ""),
        priv_key=entry.data.get(CONF_SNMP_PRIV_KEY, ""),
        auth_protocol=entry.data.get(CONF_SNMP_AUTH_PROTOCOL, DEFAULT_SNMP_AUTH_PROTOCOL),
        priv_protocol=entry.data.get(CONF_SNMP_PRIV_PROTOCOL, DEFAULT_SNMP_PRIV_PROTOCOL),
    )
    await client.async_initialize(hass)
    scan_interval = timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
    )
    coordinator = CatalystCoordinator(
        hass,
        client,
        scan_interval,
        write_enabled=(
            entry.data.get(CONF_CREDENTIAL_ACCESS, CREDENTIAL_ACCESS_READ_WRITE)
            == CREDENTIAL_ACCESS_READ_WRITE
        ),
    )
    await coordinator.async_config_entry_first_refresh()

    coordinator.snmp_mode = "3 (authPriv)" if client.version == "3" else "2c"
    coordinator.notification_listener_enabled = entry.options.get(
        CONF_TRAP_ENABLED, False
    )
    coordinator.notification_listener_port = entry.options.get(
        CONF_TRAP_PORT, DEFAULT_TRAP_PORT
    )

    mac_tracker = MacMovementTracker(hass, client.host)
    mac_tracker.observe(coordinator.data)
    coordinator.mac_movement_tracker = mac_tracker
    coordinator.mac_movement_remove_listener = coordinator.async_add_listener(
        lambda: mac_tracker.observe(coordinator.data)
    )

    entry.runtime_data = coordinator
    _remove_legacy_access_vlan_number_entities(hass, entry)
    if entry.options.get(CONF_TRAP_ENABLED, False):
        trap_receiver = CatalystTrapReceiver(
            coordinator, entry.options.get(CONF_TRAP_PORT, DEFAULT_TRAP_PORT)
        )
        await trap_receiver.async_start(hass)
        coordinator.trap_receiver = trap_receiver
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CatalystConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(
        "Unloading Cisco Catalyst config entry %s; platforms=%s",
        entry.entry_id,
        ", ".join(PLATFORMS),
    )
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        _LOGGER.error(
            "Home Assistant reported that one or more Cisco Catalyst platforms "
            "failed to unload for config entry %s; runtime resources remain open",
            entry.entry_id,
        )
        return False

    remove_listener = getattr(entry.runtime_data, "mac_movement_remove_listener", None)
    if remove_listener is not None:
        remove_listener()
    trap_receiver = getattr(entry.runtime_data, "trap_receiver", None)
    if trap_receiver is not None:
        trap_receiver.close()
    entry.runtime_data.client.close()
    _LOGGER.info("Cisco Catalyst config entry %s unloaded successfully", entry.entry_id)
    return True
