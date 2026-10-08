"""SNMP trap/inform receiver for event-driven reconciliation."""

from __future__ import annotations

import logging
from collections import deque
from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import ntfrcv

from .const import SNMP_ENGINE_ID
from .coordinator import CatalystCoordinator
from .snmp import build_warmed_engine

_LOGGER = logging.getLogger(__name__)
EVENT_SNMP_NOTIFICATION = "cisco_catalyst_snmp_notification"

_SNMP_TRAP_OID = "1.3.6.1.6.3.1.1.4.1.0"
_STANDARD_NOTIFICATION_TYPES = {
    "1.3.6.1.6.3.1.1.5.1": "cold_start",
    "1.3.6.1.6.3.1.1.5.2": "warm_start",
    "1.3.6.1.6.3.1.1.5.5": "snmp_authentication_failure",
    "1.3.6.1.2.1.47.2.0.1": "entity_config_change",
}
_LINK_NOTIFICATION_TYPES = {
    "1.3.6.1.6.3.1.1.5.3": "link_down_hint",
    "1.3.6.1.6.3.1.1.5.4": "link_up_hint",
}
_CISCO_NOTIFICATION_TYPES = {
    "1.3.6.1.4.1.9.9.109.2.0.1": "cpu_threshold_rising",
    "1.3.6.1.4.1.9.9.109.2.0.2": "cpu_threshold_falling",
    "1.3.6.1.4.1.9.9.13.3.0.1": "environment_shutdown",
    "1.3.6.1.4.1.9.9.13.3.0.2": "environment_voltage",
    "1.3.6.1.4.1.9.9.13.3.0.3": "environment_temperature",
    "1.3.6.1.4.1.9.9.13.3.0.4": "environment_fan",
    "1.3.6.1.4.1.9.9.13.3.0.5": "environment_supply",
    "1.3.6.1.4.1.9.9.13.3.0.6": "environment_voltage_status_change",
    "1.3.6.1.4.1.9.9.13.3.0.7": "environment_temperature_status_change",
    "1.3.6.1.4.1.9.9.13.3.0.8": "environment_fan_status_change",
    "1.3.6.1.4.1.9.9.13.3.0.9": "environment_supply_status_change",
    # CISCO-ERR-DISABLE-MIB. Rev1 is the RFC 2578-compliant notification;
    # retain the deprecated legacy notification for older agents.
    "1.3.6.1.4.1.9.9.548.0.2": "errdisable_interface",
    "1.3.6.1.4.1.9.9.548.0.1.1": "errdisable_interface_legacy",
    # CISCO-FLASH-MIB removable-device and low-space notifications.
    "1.3.6.1.4.1.9.9.10.1.3.0.4": "flash_device_change",
    "1.3.6.1.4.1.9.9.10.1.3.0.5": "flash_device_inserted_legacy",
    "1.3.6.1.4.1.9.9.10.1.3.0.6": "flash_device_removed_legacy",
    "1.3.6.1.4.1.9.9.10.1.3.0.7": "flash_device_inserted",
    "1.3.6.1.4.1.9.9.10.1.3.0.8": "flash_device_removed",
    "1.3.6.1.4.1.9.9.10.1.3.0.9": "flash_partition_low_space",
    "1.3.6.1.4.1.9.9.10.1.3.0.10": "flash_partition_low_space_recovery",
    "1.3.6.1.4.1.9.9.10.1.3.0.11": "flash_device_change_extended",
    "1.3.6.1.4.1.9.9.10.1.3.0.12": "flash_device_inserted_extended",
    "1.3.6.1.4.1.9.9.10.1.3.0.13": "flash_device_removed_extended",
    # CISCO-INTERFACE-XCVR-MONITOR-MIB digital diagnostics notification.
    "1.3.6.1.4.1.9.9.706.0.1": "transceiver_monitor_status_change",
}
_PETH_PSE_PORT_ON_OFF_NOTIFICATION = "1.3.6.1.2.1.105.0.1"
_PETH_PSE_PORT_DETECTION_STATUS = "1.3.6.1.2.1.105.1.1.1.6"
_IF_INDEX_OBJECT = "1.3.6.1.2.1.2.2.1.1"
_CMN_MAC_CHANGED_NOTIFICATION = "1.3.6.1.4.1.9.9.215.2.0.1"
_CMN_MAC_MOVE_NOTIFICATION = "1.3.6.1.4.1.9.9.215.2.0.2"
_CMN_MAC_MOVE_ADDRESS = "1.3.6.1.4.1.9.9.215.1.3.3.0"
_CMN_MAC_MOVE_VLAN = "1.3.6.1.4.1.9.9.215.1.3.4.0"
_CMN_MAC_MOVE_FROM_PORT = "1.3.6.1.4.1.9.9.215.1.3.5.0"
_CMN_MAC_MOVE_TO_PORT = "1.3.6.1.4.1.9.9.215.1.3.6.0"
_POE_STATUS_NAMES = {
    1: "disabled",
    2: "searching",
    3: "delivering_power",
    4: "fault",
    5: "test",
    6: "other_fault",
}
_DUPLICATE_WINDOW_SECONDS = 2.0
_STORM_WINDOW_SECONDS = 10.0
_STORM_MAX_NOTIFICATIONS = 10
_SYS_UPTIME_OID = "1.3.6.1.2.1.1.3.0"


def _notification_semantics(var_binds: dict[str, str]) -> dict[str, Any]:
    """Return stable additive semantics for known notification payloads."""
    notification_oid = var_binds.get(_SNMP_TRAP_OID, "")
    semantics: dict[str, Any] = {
        "notification_oid": notification_oid,
        "notification_type": "unknown",
    }
    simple_type = _STANDARD_NOTIFICATION_TYPES.get(
        notification_oid
    ) or _CISCO_NOTIFICATION_TYPES.get(notification_oid)
    if simple_type is not None:
        semantics["notification_type"] = simple_type
        return semantics

    link_type = _LINK_NOTIFICATION_TYPES.get(notification_oid)
    if link_type is not None:
        semantics["notification_type"] = link_type
        prefix = _IF_INDEX_OBJECT + "."
        for oid, value in var_binds.items():
            if not oid.startswith(prefix):
                continue
            try:
                semantics["if_index"] = int(value)
            except ValueError:
                try:
                    semantics["if_index"] = int(oid[len(prefix) :])
                except ValueError:
                    pass
            break
        return semantics

    if notification_oid == _CMN_MAC_CHANGED_NOTIFICATION:
        semantics["notification_type"] = "mac_table_change_hint"
        return semantics

    if notification_oid == _CMN_MAC_MOVE_NOTIFICATION:
        semantics["notification_type"] = "mac_move_hint"
        semantics["mac_address"] = var_binds.get(_CMN_MAC_MOVE_ADDRESS, "")
        for field, oid in (
            ("vlan", _CMN_MAC_MOVE_VLAN),
            ("from_bridge_port", _CMN_MAC_MOVE_FROM_PORT),
            ("to_bridge_port", _CMN_MAC_MOVE_TO_PORT),
        ):
            value = var_binds.get(oid)
            if value is None:
                continue
            try:
                semantics[field] = int(value)
            except ValueError:
                continue
        return semantics

    if notification_oid != _PETH_PSE_PORT_ON_OFF_NOTIFICATION:
        return semantics

    semantics["notification_type"] = "poe_port_status"
    prefix = _PETH_PSE_PORT_DETECTION_STATUS + "."
    for oid, value in var_binds.items():
        if not oid.startswith(prefix):
            continue
        suffix = oid[len(prefix) :]
        parts = suffix.split(".")
        if len(parts) != 2:
            continue
        try:
            group = int(parts[0])
            port = int(parts[1])
            status = int(value)
        except ValueError:
            continue
        semantics.update(
            {
                "pse_group": group,
                "pse_port": port,
                "pse_detection_status": status,
                "pse_detection_status_name": _POE_STATUS_NAMES.get(
                    status, f"unknown_{status}"
                ),
            }
        )
        break
    return semantics


def _dedupe_key(
    semantics: dict[str, Any], var_binds: dict[str, str]
) -> tuple[str, ...] | None:
    """Return a stable identity for immediate duplicate notifications."""
    notification_type = str(semantics.get("notification_type", "unknown"))
    if notification_type == "poe_port_status":
        required = ("pse_group", "pse_port", "pse_detection_status")
        if not all(key in semantics for key in required):
            return None
        return (
            "poe_port_status",
            str(semantics["pse_group"]),
            str(semantics["pse_port"]),
            str(semantics["pse_detection_status"]),
        )

    if notification_type == "unknown":
        return None

    payload_identity = tuple(
        f"{oid}={value}"
        for oid, value in sorted(var_binds.items())
        if oid not in {_SYS_UPTIME_OID, _SNMP_TRAP_OID}
    )
    return (notification_type, *payload_identity)


class _DiagnosticUdpTransport(udp.UdpTransport):
    """UDP transport that logs only packet metadata before PySNMP decoding."""

    def datagram_received(self, datagram: bytes, transport_address: Any) -> None:
        _LOGGER.debug(
            "Cisco Catalyst SNMP UDP datagram received from %s (%s bytes)",
            transport_address,
            len(datagram),
        )
        super().datagram_received(datagram, transport_address)


class CatalystTrapReceiver:
    """Receive switch notifications and trigger an authoritative refresh."""

    def __init__(self, coordinator: CatalystCoordinator, port: int) -> None:
        self.coordinator = coordinator
        self.port = port
        self._engine: engine.SnmpEngine | None = None
        self._receiver: ntfrcv.NotificationReceiver | None = None
        self._recent_notifications: dict[tuple[str, ...], float] = {}
        self._notification_times: dict[str, deque[float]] = {}

    async def async_start(self, hass: HomeAssistant) -> None:
        """Create PySNMP off-loop, then bind the UDP receiver."""
        if self._engine is None:
            self._engine = await hass.async_add_executor_job(build_warmed_engine)
        client = self.coordinator.client
        if client.version == "3":
            # SNMPv3 TRAPs are authoritative at the sending switch. PySNMP
            # therefore needs the switch's engine ID when localizing the USM
            # auth/privacy keys for inbound notifications.
            security_engine_id = await client.get(SNMP_ENGINE_ID)
            auth_protocol = {
                "sha": config.USM_AUTH_HMAC96_SHA,
                "sha256": config.USM_AUTH_HMAC192_SHA256,
            }.get(client.auth_protocol, config.USM_AUTH_HMAC192_SHA256)
            priv_protocol = {
                "aes128": config.USM_PRIV_CFB128_AES,
            }.get(client.priv_protocol, config.USM_PRIV_CFB128_AES)
            # INFORMs reverse the authoritative-engine relationship: the
            # receiver is authoritative. Register the same USM credentials for
            # the local engine as well as for the switch engine used by TRAPs.
            config.add_v3_user(
                self._engine,
                client.username,
                auth_protocol,
                client.auth_key,
                priv_protocol,
                client.priv_key,
            )
            config.add_v3_user(
                self._engine,
                client.username,
                auth_protocol,
                client.auth_key,
                priv_protocol,
                client.priv_key,
                securityEngineId=security_engine_id,
            )
        else:
            config.add_v1_system(self._engine, "cisco-catalyst", client.read_community)

        transport = _DiagnosticUdpTransport().open_server_mode(("0.0.0.0", self.port))
        config.add_transport(
            self._engine,
            udp.DOMAIN_NAME,
            transport,
        )
        self._receiver = ntfrcv.NotificationReceiver(self._engine, self._notification)
        _LOGGER.debug(
            "Cisco Catalyst SNMP notification receiver configured on UDP %s "
            "(SNMP version %s)",
            self.port,
            client.version,
        )

    def _enrich_interface_semantics(self, semantics: dict[str, Any]) -> None:
        """Resolve bridge-port identifiers through the latest authoritative poll."""
        if semantics.get("notification_type") != "mac_move_hint":
            return
        data = getattr(self.coordinator, "data", None)
        if data is None:
            return
        bridge_map = getattr(data, "bridge_port_ifindex", {})
        interfaces = getattr(data, "interfaces", {})
        for direction in ("from", "to"):
            bridge_port = semantics.get(f"{direction}_bridge_port")
            if bridge_port is None:
                continue
            if_index = bridge_map.get(bridge_port)
            if if_index is None:
                continue
            semantics[f"{direction}_if_index"] = if_index
            interface = interfaces.get(if_index)
            if interface is None:
                continue
            semantics[f"{direction}_interface"] = interface.name
            if interface.description:
                semantics[f"{direction}_interface_description"] = interface.description

    def _is_duplicate(
        self, semantics: dict[str, Any], var_binds: dict[str, str]
    ) -> bool:
        """Suppress immediate retransmits of the same semantic notification."""
        key = _dedupe_key(semantics, var_binds)
        if key is None:
            return False
        now = monotonic()
        cutoff = now - _DUPLICATE_WINDOW_SECONDS
        self._recent_notifications = {
            item: seen
            for item, seen in self._recent_notifications.items()
            if seen >= cutoff
        }
        previous = self._recent_notifications.get(key)
        self._recent_notifications[key] = now
        return previous is not None and previous >= cutoff

    def _is_rate_limited(self, semantics: dict[str, Any]) -> bool:
        """Bound notification storms while polling remains authoritative."""
        notification_type = str(semantics.get("notification_type", "unknown"))
        if notification_type == "unknown":
            notification_type = str(semantics.get("notification_oid", "unknown"))
        now = monotonic()
        cutoff = now - _STORM_WINDOW_SECONDS
        recent = self._notification_times.setdefault(notification_type, deque())
        while recent and recent[0] < cutoff:
            recent.popleft()
        if len(recent) >= _STORM_MAX_NOTIFICATIONS:
            return True
        recent.append(now)
        return False

    def _notification(
        self,
        _engine: engine.SnmpEngine,
        _state_reference: Any,
        context_engine_id: Any,
        context_name: Any,
        var_binds: list[tuple[Any, Any]],
        _context: Any,
    ) -> None:
        """Publish a diagnostic HA event, then reconcile state from the switch."""
        _LOGGER.debug(
            "Cisco Catalyst SNMP notification decoded successfully for %s",
            self.coordinator.client.host,
        )
        receiver_engine_id = (
            self._engine.snmpEngineID.prettyPrint() if self._engine is not None else ""
        )
        var_bind_values = {
            oid.prettyPrint(): value.prettyPrint() for oid, value in var_binds
        }
        semantics = _notification_semantics(var_bind_values)
        self._enrich_interface_semantics(semantics)
        if self._is_duplicate(semantics, var_bind_values):
            _LOGGER.debug(
                "Cisco Catalyst duplicate SNMP notification suppressed for %s: %s",
                self.coordinator.client.host,
                _dedupe_key(semantics, var_bind_values),
            )
            return
        if self._is_rate_limited(semantics):
            _LOGGER.warning(
                "Cisco Catalyst SNMP notification storm limited for %s: %s",
                self.coordinator.client.host,
                semantics.get("notification_type", "unknown"),
            )
            return
        payload = {
            "host": self.coordinator.client.host,
            "receiver_engine_id": receiver_engine_id,
            "context_engine_id": context_engine_id.prettyPrint() if context_engine_id else "",
            "context_name": context_name.prettyPrint() if context_name else "",
            **semantics,
            "var_binds": var_bind_values,
        }
        self.coordinator.hass.bus.async_fire(EVENT_SNMP_NOTIFICATION, payload)
        self.coordinator.hass.async_create_task(self.coordinator.async_request_refresh())

    def close(self) -> None:
        """Release the notification receiver and UDP transport."""
        if self._receiver is not None and self._engine is not None:
            self._receiver.close(self._engine)
            self._receiver = None
        if self._engine is not None:
            self._engine.close_dispatcher()
            self._engine = None
