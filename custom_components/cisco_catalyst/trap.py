"""SNMP trap/inform receiver for event-driven reconciliation."""

from __future__ import annotations

import logging
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

    def _notification(
        self,
        _engine: engine.SnmpEngine,
        _state_reference: Any,
        context_engine_id: Any,
        context_name: Any,
        var_binds: list[tuple[Any, Any]],
        _context: Any,
    ) -> None:
        """Publish a HA event, then reconcile state from the switch."""
        _LOGGER.debug(
            "Cisco Catalyst SNMP notification decoded successfully for %s",
            self.coordinator.client.host,
        )
        receiver_engine_id = (
            self._engine.snmpEngineID.prettyPrint() if self._engine is not None else ""
        )
        payload = {
            "host": self.coordinator.client.host,
            "receiver_engine_id": receiver_engine_id,
            "context_engine_id": context_engine_id.prettyPrint() if context_engine_id else "",
            "context_name": context_name.prettyPrint() if context_name else "",
            "var_binds": {
                oid.prettyPrint(): value.prettyPrint() for oid, value in var_binds
            },
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
