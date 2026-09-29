"""Asynchronous SNMPv2c/SNMPv3 client used by the integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    USM_AUTH_HMAC96_SHA,
    USM_AUTH_HMAC192_SHA256,
    USM_PRIV_CFB128_AES,
    bulk_walk_cmd,
    get_cmd,
    set_cmd,
)
from pysnmp.proto.rfc1902 import Integer, OctetString


# PySNMP uses these internal MIBs while constructing/using the v3arch engine even
# when all application OIDs are numeric and lookupMib=False. Load the complete
# protocol dependency set before the engine is first used on HA's event loop.
_CORE_MIB_MODULES = (
    "SNMPv2-SMI",
    "SNMPv2-TC",
    "SNMPv2-CONF",
    "SNMPv2-TM",
    "SNMPv2-MIB",
    "SNMP-FRAMEWORK-MIB",
    "SNMP-MPD-MIB",
    "SNMP-USER-BASED-SM-MIB",
    "SNMP-VIEW-BASED-ACM-MIB",
    "SNMP-COMMUNITY-MIB",
    "PYSNMP-SOURCE-MIB",
)


def build_warmed_engine() -> SnmpEngine:
    """Build an engine and force PySNMP's protocol MIB disk I/O now."""
    snmp_engine = SnmpEngine()
    snmp_engine.get_mib_builder().load_modules(*_CORE_MIB_MODULES)
    return snmp_engine


class CatalystSnmpError(Exception):
    """Raised when an SNMP operation fails."""


class CatalystSnmpClient:
    """SNMP client for a Catalyst switch."""

    def __init__(
        self,
        host: str,
        port: int,
        read_community: str = "",
        write_community: str = "",
        *,
        version: str = "2c",
        username: str = "",
        auth_key: str = "",
        priv_key: str = "",
        auth_protocol: str = "sha256",
        priv_protocol: str = "aes128",
    ) -> None:
        self.host = host
        self.port = port
        self.read_community = read_community
        self.write_community = write_community
        self.version = version
        self.username = username
        self.auth_key = auth_key
        self.priv_key = priv_key
        self.auth_protocol = auth_protocol
        self.priv_protocol = priv_protocol
        self._engine: SnmpEngine | None = None

    async def async_initialize(self, hass: HomeAssistant) -> None:
        """Create PySNMP's engine off the Home Assistant event loop.

        SnmpEngine construction loads MIB modules from disk synchronously.
        """
        if self._engine is None:
            self._engine = await hass.async_add_executor_job(build_warmed_engine)

    def _require_engine(self) -> SnmpEngine:
        if self._engine is None:
            raise CatalystSnmpError("SNMP client has not been initialized")
        return self._engine

    async def _target(self) -> UdpTransportTarget:
        return await UdpTransportTarget.create((self.host, self.port), timeout=2, retries=1)

    def _auth(self, *, write: bool = False) -> CommunityData | UsmUserData:
        if self.version == "3":
            auth_protocols = {
                "sha": USM_AUTH_HMAC96_SHA,
                "sha256": USM_AUTH_HMAC192_SHA256,
            }
            priv_protocols = {"aes128": USM_PRIV_CFB128_AES}
            return UsmUserData(
                self.username,
                authKey=self.auth_key or None,
                privKey=self.priv_key or None,
                authProtocol=auth_protocols.get(self.auth_protocol, USM_AUTH_HMAC192_SHA256),
                privProtocol=priv_protocols.get(self.priv_protocol, USM_PRIV_CFB128_AES),
            )
        return CommunityData(self.write_community if write else self.read_community, mpModel=1)

    @staticmethod
    def _check(error_indication: Any, error_status: Any) -> None:
        if error_indication:
            raise CatalystSnmpError(str(error_indication))
        if error_status:
            raise CatalystSnmpError(error_status.prettyPrint())

    async def get(self, oid: str) -> Any:
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            self._require_engine(),
            self._auth(),
            await self._target(),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lookupMib=False,
        )
        self._check(error_indication, error_status)
        return var_binds[0][1]

    async def walk(self, oid: str) -> dict[str, Any]:
        results: dict[str, Any] = {}
        iterator = bulk_walk_cmd(
            self._require_engine(),
            self._auth(),
            await self._target(),
            ContextData(),
            0,
            25,
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
            lookupMib=False,
        )
        async for error_indication, error_status, _error_index, var_binds in iterator:
            self._check(error_indication, error_status)
            for var_bind in var_binds:
                results[var_bind[0].prettyPrint()] = var_bind[1]
        return results

    async def _set(self, oid: str, value: Any) -> None:
        error_indication, error_status, _error_index, _var_binds = await set_cmd(
            self._require_engine(),
            self._auth(write=True),
            await self._target(),
            ContextData(),
            ObjectType(ObjectIdentity(oid), value),
            lookupMib=False,
        )
        self._check(error_indication, error_status)

    async def set_integer(self, oid: str, value: int) -> None:
        """Write an INTEGER."""
        await self._set(oid, Integer(value))

    async def set_string(self, oid: str, value: str) -> None:
        """Write an OCTET STRING."""
        await self._set(oid, OctetString(value))

    def close(self) -> None:
        """Release PySNMP dispatcher resources."""
        if self._engine is not None:
            self._engine.close_dispatcher()
            self._engine = None
