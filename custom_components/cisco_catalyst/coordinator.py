"""Data coordinator for Cisco Catalyst."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import ipaddress
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CDP_CACHE_ADDRESS,
    CDP_CACHE_DEVICE_ID,
    CDP_CACHE_DEVICE_PORT,
    CDP_CACHE_PLATFORM,
    CEFC_FAN_TRAY_OPER_STATUS,
    CEFC_FRU_POWER_OPER_STATUS,
    CISCO_ENTITY_SENSOR_PRECISION,
    CISCO_ENTITY_SENSOR_SCALE,
    CISCO_ENTITY_SENSOR_SCALE_EXPONENT,
    CISCO_ENTITY_SENSOR_STATUS,
    CISCO_ENTITY_SENSOR_TYPE,
    CISCO_ENTITY_SENSOR_TYPE_CELSIUS,
    CISCO_ENTITY_SENSOR_UPDATE_RATE,
    CISCO_ENTITY_SENSOR_VALUE,
    CISCO_MEMORY_POOL_FREE,
    CISCO_MEMORY_POOL_LARGEST_FREE,
    CISCO_MEMORY_POOL_NAME,
    CISCO_MEMORY_POOL_USED,
    CISCO_VM_VLAN,
    CISCO_VM_VLAN_TYPE,
    CISCO_VTP_TRUNK_DYNAMIC_STATUS,
    CISCO_VTP_VLAN_STATE,
    CISCO_VTP_VLAN_STATE_OPERATIONAL,
    CISCO_VTP_TRUNK_NATIVE_VLAN,
    CISCO_VTP_TRUNK_VLANS_ENABLED,
    CISCO_VTP_TRUNK_VLANS_ENABLED_2K,
    CISCO_VTP_TRUNK_VLANS_ENABLED_3K,
    CISCO_VTP_TRUNK_VLANS_ENABLED_4K,
    CPM_CPU_1MIN_REV,
    CPM_CPU_5MIN_REV,
    CPM_CPU_5SEC_REV,
    CPE_PORT_DEVICE_DETECTED,
    CPE_PORT_ENABLE,
    CPE_PORT_ENT_PHY_INDEX,
    CPE_PORT_MAX_POWER_DRAWN,
    CPE_PORT_POWER_ALLOCATED,
    CPE_PORT_POWER_AVAILABLE,
    CPE_PORT_POWER_CONSUMPTION,
    DOT1D_BASE_PORT_IFINDEX,
    DOT1D_TP_FDB_PORT,
    ENT_PHYSICAL_CLASS,
    ENT_PHYSICAL_CLASS_CHASSIS,
    ENT_PHYSICAL_MODEL_NAME,
    ENT_PHYSICAL_NAME,
    ENT_PHYSICAL_SERIAL_NUM,
    ENT_PHYSICAL_SOFTWARE_REV,
    IF_ADMIN_STATUS,
    IF_ALIAS,
    IF_HC_IN_OCTETS,
    IF_HC_OUT_OCTETS,
    IF_HIGH_SPEED,
    IF_IN_DISCARDS,
    IF_IN_ERRORS,
    IF_NAME,
    IF_OPER_STATUS,
    IF_OUT_DISCARDS,
    IF_OUT_ERRORS,
    IP_NET_TO_MEDIA_PHYS_ADDRESS,
    LLDP_LOC_PORT_DESC,
    LLDP_LOC_PORT_ID,
    LLDP_REM_CHASSIS_ID,
    LLDP_REM_PORT_DESC,
    LLDP_REM_PORT_ID,
    LLDP_REM_SYS_NAME,
    PETH_MAIN_PSE_POWER,
    PETH_MAIN_PSE_CONSUMPTION_POWER,
    SYS_DESCR,
    SYS_NAME,
    SYS_UPTIME,
)
from .snmp import CatalystSnmpClient, CatalystSnmpError

_LOGGER = logging.getLogger(__name__)
_PHYSICAL_PORT_RE = re.compile(r"^(?:GigabitEthernet|TwentyFiveGigE|TenGigabitEthernet|FortyGigabitEthernet)\d+/\d+/\d+$")
_SHORT_INTERFACE_RE = re.compile(r"^(Twe|Gi|Te|Fo)(\d+(?:/\d+)+)$")
_SHORT_TO_LONG_PREFIX = {
    "Twe": "TwentyFiveGigE",
    "Gi": "GigabitEthernet",
    "Te": "TenGigabitEthernet",
    "Fo": "FortyGigabitEthernet",
}


@dataclass(frozen=True)
class CdpNeighbor:
    device_id: str = ""
    address: str | None = None
    port_id: str = ""
    platform: str = ""


@dataclass(frozen=True)
class LldpNeighbor:
    system_name: str = ""
    chassis_id: str = ""
    port_id: str = ""
    port_description: str = ""


@dataclass(frozen=True)
class ChassisData:
    ent_index: int
    name: str = ""
    model: str = ""
    serial: str = ""
    software_rev: str = ""


@dataclass(frozen=True)
class TemperatureSensorData:
    ent_index: int
    name: str
    value_celsius: float
    status: int
    update_rate: int | None = None


@dataclass(frozen=True)
class FruStatusData:
    ent_index: int
    name: str
    status: int


@dataclass(frozen=True)
class CpuData:
    index: str
    five_seconds: int | None = None
    one_minute: int | None = None
    five_minutes: int | None = None


@dataclass(frozen=True)
class MemoryData:
    index: str
    name: str
    used_bytes: int
    free_bytes: int
    largest_free_bytes: int | None = None

    @property
    def total_bytes(self) -> int:
        return self.used_bytes + self.free_bytes

    @property
    def used_percent(self) -> float | None:
        if self.total_bytes <= 0:
            return None
        return self.used_bytes * 100 / self.total_bytes


@dataclass
class InterfaceData:
    if_index: int
    name: str
    description: str = ""
    admin_status: int | None = None
    oper_status: int | None = None
    speed_mbps: int | None = None
    in_octets: int | None = None
    out_octets: int | None = None
    in_errors: int | None = None
    out_errors: int | None = None
    in_discards: int | None = None
    out_discards: int | None = None
    access_vlan: int | None = None
    access_vlan_type: int | None = None
    is_trunk: bool | None = None
    native_vlan: int | None = None
    allowed_vlans: list[int] = field(default_factory=list)
    mac_addresses: list[str] = field(default_factory=list)
    ip_addresses: list[str] = field(default_factory=list)
    cdp_neighbors: list[CdpNeighbor] = field(default_factory=list)
    lldp_neighbors: list[LldpNeighbor] = field(default_factory=list)


@dataclass
class PoePortData:
    index: str
    name: str
    enabled: bool
    device_detected: bool | None = None
    power_allocated_mw: int | None = None
    power_available_mw: int | None = None
    power_consumption_mw: int | None = None
    max_power_drawn_mw: int | None = None


@dataclass
class CatalystData:
    sys_name: str
    sys_descr: str
    uptime_ticks: int
    interfaces: dict[int, InterfaceData]
    poe_ports: dict[str, PoePortData]
    bridge_port_ifindex: dict[int, int] = field(default_factory=dict)
    operational_vlans: set[int] = field(default_factory=set)
    chassis: ChassisData | None = None
    temperatures: dict[int, TemperatureSensorData] = field(default_factory=dict)
    power_supplies: dict[int, FruStatusData] = field(default_factory=dict)
    fans: dict[int, FruStatusData] = field(default_factory=dict)
    cpu: CpuData | None = None
    memory: MemoryData | None = None
    poe_budget_w: int | None = None
    poe_used_w: int | None = None


def _suffix(oid: str, base: str) -> str:
    return oid.removeprefix(base + ".")


def _int(value: Any) -> int:
    return int(value)


def _text(value: Any) -> str:
    try:
        return value.prettyPrint()
    except AttributeError:
        return str(value)


def _octets(value: Any) -> bytes:
    try:
        return bytes(value.asOctets())
    except AttributeError:
        try:
            return bytes(value)
        except (TypeError, ValueError):
            return b""


def _mac_from_fdb_suffix(suffix: str) -> str | None:
    try:
        parts = [int(part) for part in suffix.split(".")]
    except ValueError:
        return None
    if len(parts) != 6 or not all(0 <= part <= 255 for part in parts):
        return None
    return ":".join(f"{part:02x}" for part in parts)


def _mac_from_value(value: Any) -> str | None:
    raw = _octets(value)
    return ":".join(f"{part:02x}" for part in raw) if len(raw) == 6 else None


def _ipv4_from_value(value: Any) -> str | None:
    raw = _octets(value)
    return str(ipaddress.IPv4Address(raw)) if len(raw) == 4 else None


def _canonical_interface_name(name: str) -> str:
    match = _SHORT_INTERFACE_RE.match(name)
    return name if match is None else _SHORT_TO_LONG_PREFIX[match.group(1)] + match.group(2)


def _table_int(table: dict[str, Any], base: str, index: str) -> int | None:
    value = table.get(f"{base}.{index}")
    return int(value) if value is not None else None


def _optional_table_int(table: dict[str, Any], base: str, index: int) -> int | None:
    value = table.get(f"{base}.{index}")
    return int(value) if value is not None else None


def _decode_vlan_bitmap(value: Any, offset: int = 0) -> list[int]:
    """Decode Cisco's MSB-first VLAN bitmap, omitting reserved VLAN indexes."""
    raw = _octets(value)
    vlans = [
        offset + byte_index * 8 + bit
        for byte_index, octet in enumerate(raw)
        for bit in range(8)
        if octet & (0x80 >> bit)
    ]
    return [vlan for vlan in vlans if 1 <= vlan <= 4094]


def _operational_vlan_ids(table: dict[str, Any]) -> set[int]:
    """Return operational VLAN IDs from CISCO-VTP-MIB vtpVlanState."""
    result: set[int] = set()
    for oid, value in table.items():
        try:
            vlan_id = int(_suffix(oid, CISCO_VTP_VLAN_STATE).split(".")[-1])
            if int(value) == CISCO_VTP_VLAN_STATE_OPERATIONAL:
                result.add(vlan_id)
        except (TypeError, ValueError):
            continue
    return result


class CatalystCoordinator(DataUpdateCoordinator[CatalystData]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: CatalystSnmpClient,
        update_interval: timedelta,
        *,
        write_enabled: bool = True,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="Cisco Catalyst",
            update_interval=update_interval,
        )
        self.client = client
        self.write_enabled = write_enabled
        # Serialize write/readback/refresh transactions so overlapping HA switch
        # services cannot publish mixed coordinator snapshots.
        self.write_lock = asyncio.Lock()
        # Prevent scheduled/trap polls from overlapping a write/readback transaction.
        self.io_lock = asyncio.Lock()
        # Requested write values override stale poll snapshots until exact-OID
        # verification and a reconciliation refresh have completed.
        self.pending_writes: dict[str, Any] = {}
        self._static_get_cache: dict[str, Any] = {}
        self._static_walk_cache: dict[str, dict[str, Any]] = {}

    async def _get_static(self, oid: str) -> Any:
        """Read a scalar once per coordinator lifetime."""
        if oid not in self._static_get_cache:
            self._static_get_cache[oid] = await self.client.get(oid)
        return self._static_get_cache[oid]

    async def _walk_static(self, oid: str) -> dict[str, Any]:
        """Walk topology/inventory data once per coordinator lifetime."""
        if oid not in self._static_walk_cache:
            self._static_walk_cache[oid] = await self.client.walk(oid)
        return self._static_walk_cache[oid]

    async def _walk_optional(self, oid: str, *, static: bool = False) -> dict[str, Any]:
        """Walk an optional MIB table without failing the whole integration."""
        try:
            return await (self._walk_static(oid) if static else self.client.walk(oid))
        except CatalystSnmpError as err:
            _LOGGER.debug("Optional SNMP table %s unavailable: %s", oid, err)
            return {}

    async def _async_update_data(self) -> CatalystData:
        """Serialize polling against SNMP write/readback transactions."""
        async with self.io_lock:
            return await self._async_update_data_locked()

    async def _async_update_data_locked(self) -> CatalystData:
        try:
            r = await asyncio.gather(
                self.client.get(SYS_NAME),
                self._get_static(SYS_DESCR),
                self.client.get(SYS_UPTIME),
                self._walk_static(IF_NAME),
                self.client.walk(IF_ALIAS),
                self.client.walk(IF_ADMIN_STATUS),
                self.client.walk(IF_OPER_STATUS),
                self.client.walk(IF_HIGH_SPEED),
                self.client.walk(IF_HC_IN_OCTETS),
                self.client.walk(IF_HC_OUT_OCTETS),
                self.client.walk(IF_IN_ERRORS),
                self.client.walk(IF_OUT_ERRORS),
                self.client.walk(IF_IN_DISCARDS),
                self.client.walk(IF_OUT_DISCARDS),
                self._walk_optional(CISCO_VM_VLAN_TYPE),
                self._walk_optional(CISCO_VM_VLAN),
                self._walk_optional(CISCO_VTP_VLAN_STATE),
                self._walk_optional(CISCO_VTP_TRUNK_DYNAMIC_STATUS),
                self._walk_optional(CISCO_VTP_TRUNK_NATIVE_VLAN),
                self._walk_optional(CISCO_VTP_TRUNK_VLANS_ENABLED),
                self._walk_optional(CISCO_VTP_TRUNK_VLANS_ENABLED_2K),
                self._walk_optional(CISCO_VTP_TRUNK_VLANS_ENABLED_3K),
                self._walk_optional(CISCO_VTP_TRUNK_VLANS_ENABLED_4K),
                self._walk_optional(LLDP_LOC_PORT_ID),
                self._walk_optional(LLDP_LOC_PORT_DESC),
                self._walk_optional(LLDP_REM_CHASSIS_ID),
                self._walk_optional(LLDP_REM_PORT_ID),
                self._walk_optional(LLDP_REM_PORT_DESC),
                self._walk_optional(LLDP_REM_SYS_NAME),
                self._walk_optional(PETH_MAIN_PSE_POWER),
                self._walk_optional(PETH_MAIN_PSE_CONSUMPTION_POWER),
                self._walk_optional(CPE_PORT_ENABLE),
                self._walk_optional(CPE_PORT_ENT_PHY_INDEX, static=True),
                self._walk_optional(CPE_PORT_DEVICE_DETECTED),
                self._walk_optional(CPE_PORT_POWER_ALLOCATED),
                self._walk_optional(CPE_PORT_POWER_AVAILABLE),
                self._walk_optional(CPE_PORT_POWER_CONSUMPTION),
                self._walk_optional(CPE_PORT_MAX_POWER_DRAWN),
                self._walk_optional(DOT1D_BASE_PORT_IFINDEX),
                self._walk_optional(DOT1D_TP_FDB_PORT),
                self._walk_optional(IP_NET_TO_MEDIA_PHYS_ADDRESS),
                self._walk_optional(CDP_CACHE_ADDRESS),
                self._walk_optional(CDP_CACHE_DEVICE_ID),
                self._walk_optional(CDP_CACHE_DEVICE_PORT),
                self._walk_optional(CDP_CACHE_PLATFORM),
                self._walk_optional(ENT_PHYSICAL_CLASS, static=True),
                self._walk_optional(ENT_PHYSICAL_NAME, static=True),
                self._walk_optional(ENT_PHYSICAL_MODEL_NAME, static=True),
                self._walk_optional(ENT_PHYSICAL_SERIAL_NUM, static=True),
                self._walk_optional(ENT_PHYSICAL_SOFTWARE_REV, static=True),
                self._walk_optional(CISCO_ENTITY_SENSOR_TYPE, static=True),
                self._walk_optional(CISCO_ENTITY_SENSOR_SCALE, static=True),
                self._walk_optional(CISCO_ENTITY_SENSOR_PRECISION, static=True),
                self._walk_optional(CISCO_ENTITY_SENSOR_VALUE),
                self._walk_optional(CISCO_ENTITY_SENSOR_STATUS),
                self._walk_optional(CISCO_ENTITY_SENSOR_UPDATE_RATE, static=True),
                self._walk_optional(CEFC_FRU_POWER_OPER_STATUS),
                self._walk_optional(CEFC_FAN_TRAY_OPER_STATUS),
                self._walk_optional(CPM_CPU_5SEC_REV),
                self._walk_optional(CPM_CPU_1MIN_REV),
                self._walk_optional(CPM_CPU_5MIN_REV),
                self._walk_optional(CISCO_MEMORY_POOL_NAME, static=True),
                self._walk_optional(CISCO_MEMORY_POOL_USED),
                self._walk_optional(CISCO_MEMORY_POOL_FREE),
                self._walk_optional(CISCO_MEMORY_POOL_LARGEST_FREE),
            )
            (
                sys_name_value,
                sys_descr_value,
                uptime_value,
                if_names,
                aliases,
                admin,
                oper,
                high_speed,
                in_octets,
                out_octets,
                in_errors,
                out_errors,
                in_discards,
                out_discards,
                access_vlan_types,
                access_vlans,
                vlan_states,
                trunk_status,
                trunk_native_vlans,
                trunk_vlans_1k,
                trunk_vlans_2k,
                trunk_vlans_3k,
                trunk_vlans_4k,
                lldp_local_ids,
                lldp_local_descs,
                lldp_chassis_ids,
                lldp_port_ids,
                lldp_port_descs,
                lldp_sys_names,
                main_pse_power,
                main_pse_consumption,
                poe_enable,
                poe_ent_index,
                poe_detected,
                poe_allocated,
                poe_available,
                poe_consumption,
                poe_max_drawn,
                bridge_port_ifindex,
                fdb_ports,
                arp_phys,
                cdp_addresses,
                cdp_device_ids,
                cdp_ports,
                cdp_platforms,
                ent_classes,
                ent_names,
                ent_models,
                ent_serials,
                ent_software,
                sensor_types,
                sensor_scales,
                sensor_precision,
                sensor_values,
                sensor_status,
                sensor_update_rates,
                fru_power_status,
                fan_status,
                cpu_5sec,
                cpu_1min,
                cpu_5min,
                memory_names,
                memory_used,
                memory_free,
                memory_largest_free,
            ) = r

            interfaces: dict[int, InterfaceData] = {}
            physical_names: set[str] = set()
            for oid, value in if_names.items():
                idx = int(_suffix(oid, IF_NAME))
                name = _canonical_interface_name(_text(value))
                if not _PHYSICAL_PORT_RE.match(name):
                    continue
                physical_names.add(name)
                alias = aliases.get(f"{IF_ALIAS}.{idx}")
                interfaces[idx] = InterfaceData(
                    if_index=idx,
                    name=name,
                    description=_text(alias) if alias is not None else "",
                    admin_status=_optional_table_int(admin, IF_ADMIN_STATUS, idx),
                    oper_status=_optional_table_int(oper, IF_OPER_STATUS, idx),
                    speed_mbps=_optional_table_int(high_speed, IF_HIGH_SPEED, idx),
                    in_octets=_optional_table_int(in_octets, IF_HC_IN_OCTETS, idx),
                    out_octets=_optional_table_int(out_octets, IF_HC_OUT_OCTETS, idx),
                    in_errors=_optional_table_int(in_errors, IF_IN_ERRORS, idx),
                    out_errors=_optional_table_int(out_errors, IF_OUT_ERRORS, idx),
                    in_discards=_optional_table_int(in_discards, IF_IN_DISCARDS, idx),
                    out_discards=_optional_table_int(out_discards, IF_OUT_DISCARDS, idx),
                    access_vlan=_optional_table_int(access_vlans, CISCO_VM_VLAN, idx),
                    access_vlan_type=_optional_table_int(
                        access_vlan_types, CISCO_VM_VLAN_TYPE, idx
                    ),
                    is_trunk=(
                        _optional_table_int(
                            trunk_status, CISCO_VTP_TRUNK_DYNAMIC_STATUS, idx
                        )
                        == 1
                        if _optional_table_int(
                            trunk_status, CISCO_VTP_TRUNK_DYNAMIC_STATUS, idx
                        )
                        is not None
                        else None
                    ),
                    native_vlan=(
                        _optional_table_int(
                            trunk_native_vlans, CISCO_VTP_TRUNK_NATIVE_VLAN, idx
                        )
                        if _optional_table_int(
                            trunk_status, CISCO_VTP_TRUNK_DYNAMIC_STATUS, idx
                        ) == 1
                        else None
                    ),
                    # Cisco exposes the trunk bitmap on access ports too. Ignore it
                    # unless the dynamic trunk status says this interface is trunking.
                    allowed_vlans=(
                        _decode_vlan_bitmap(
                            trunk_vlans_1k.get(
                                f"{CISCO_VTP_TRUNK_VLANS_ENABLED}.{idx}"
                            )
                        )
                        + _decode_vlan_bitmap(
                            trunk_vlans_2k.get(
                                f"{CISCO_VTP_TRUNK_VLANS_ENABLED_2K}.{idx}"
                            ),
                            1024,
                        )
                        + _decode_vlan_bitmap(
                            trunk_vlans_3k.get(
                                f"{CISCO_VTP_TRUNK_VLANS_ENABLED_3K}.{idx}"
                            ),
                            2048,
                        )
                        + _decode_vlan_bitmap(
                            trunk_vlans_4k.get(
                                f"{CISCO_VTP_TRUNK_VLANS_ENABLED_4K}.{idx}"
                            ),
                            3072,
                        )
                        if _optional_table_int(
                            trunk_status, CISCO_VTP_TRUNK_DYNAMIC_STATUS, idx
                        ) == 1
                        else []
                    ),
                )

            operational_vlans = _operational_vlan_ids(vlan_states)

            bridge_port_ifindex_map: dict[int, int] = {}
            for oid, value in bridge_port_ifindex.items():
                try:
                    bridge_port = int(_suffix(oid, DOT1D_BASE_PORT_IFINDEX))
                    bridge_port_ifindex_map[bridge_port] = int(value)
                except (TypeError, ValueError):
                    continue

            self._correlate_fdb_and_arp(
                interfaces, bridge_port_ifindex, fdb_ports, arp_phys
            )
            self._correlate_cdp(
                interfaces,
                cdp_addresses,
                cdp_device_ids,
                cdp_ports,
                cdp_platforms,
            )
            self._correlate_lldp(
                interfaces,
                lldp_local_ids,
                lldp_local_descs,
                lldp_chassis_ids,
                lldp_port_ids,
                lldp_port_descs,
                lldp_sys_names,
            )
            chassis = self._find_chassis(
                ent_classes, ent_names, ent_models, ent_serials, ent_software
            )
            temperatures = self._find_temperatures(
                sensor_types,
                sensor_scales,
                sensor_precision,
                sensor_values,
                sensor_status,
                sensor_update_rates,
                ent_names,
            )
            power_supplies = self._find_fru_status(
                fru_power_status, CEFC_FRU_POWER_OPER_STATUS, ent_names
            )
            fans = self._find_fru_status(
                fan_status, CEFC_FAN_TRAY_OPER_STATUS, ent_names
            )
            cpu = self._find_cpu(cpu_5sec, cpu_1min, cpu_5min)
            memory = self._find_processor_memory(
                memory_names, memory_used, memory_free, memory_largest_free
            )

            poe_ports: dict[str, PoePortData] = {}
            for oid, value in poe_enable.items():
                index = _suffix(oid, CPE_PORT_ENABLE)
                ent_value = poe_ent_index.get(f"{CPE_PORT_ENT_PHY_INDEX}.{index}")
                if ent_value is None:
                    continue
                ent_name = ent_names.get(f"{ENT_PHYSICAL_NAME}.{int(ent_value)}")
                if ent_name is None:
                    continue
                name = _canonical_interface_name(_text(ent_name))
                if name not in physical_names:
                    continue
                detected = _table_int(poe_detected, CPE_PORT_DEVICE_DETECTED, index)
                poe_ports[index] = PoePortData(
                    index=index,
                    name=name,
                    enabled=int(value) != 4,
                    device_detected=detected == 1 if detected is not None else None,
                    power_allocated_mw=_table_int(
                        poe_allocated, CPE_PORT_POWER_ALLOCATED, index
                    ),
                    power_available_mw=_table_int(
                        poe_available, CPE_PORT_POWER_AVAILABLE, index
                    ),
                    power_consumption_mw=_table_int(
                        poe_consumption, CPE_PORT_POWER_CONSUMPTION, index
                    ),
                    max_power_drawn_mw=_table_int(
                        poe_max_drawn, CPE_PORT_MAX_POWER_DRAWN, index
                    ),
                )

            return CatalystData(
                sys_name=_text(sys_name_value),
                sys_descr=_text(sys_descr_value),
                uptime_ticks=_int(uptime_value),
                interfaces=interfaces,
                poe_ports=poe_ports,
                bridge_port_ifindex=bridge_port_ifindex_map,
                operational_vlans=operational_vlans,
                chassis=chassis,
                temperatures=temperatures,
                power_supplies=power_supplies,
                fans=fans,
                cpu=cpu,
                memory=memory,
                poe_budget_w=sum(int(value) for value in main_pse_power.values()) or None,
                poe_used_w=sum(int(value) for value in main_pse_consumption.values()) or None,
            )
        except (CatalystSnmpError, ValueError, TypeError) as err:
            raise UpdateFailed(f"SNMP update failed: {err}") from err

    @staticmethod
    def _find_cpu(five_sec, one_min, five_min) -> CpuData | None:
        indexes = sorted(
            {_suffix(oid, CPM_CPU_5SEC_REV) for oid in five_sec}
            | {_suffix(oid, CPM_CPU_1MIN_REV) for oid in one_min}
            | {_suffix(oid, CPM_CPU_5MIN_REV) for oid in five_min},
            key=lambda value: tuple(int(part) for part in value.split(".")),
        )
        if not indexes:
            return None
        index = indexes[0]
        return CpuData(
            index=index,
            five_seconds=_table_int(five_sec, CPM_CPU_5SEC_REV, index),
            one_minute=_table_int(one_min, CPM_CPU_1MIN_REV, index),
            five_minutes=_table_int(five_min, CPM_CPU_5MIN_REV, index),
        )

    @staticmethod
    def _find_processor_memory(names, used, free, largest_free) -> MemoryData | None:
        for oid, value in names.items():
            if _text(value).strip().lower() != "processor":
                continue
            index = _suffix(oid, CISCO_MEMORY_POOL_NAME)
            used_value = _table_int(used, CISCO_MEMORY_POOL_USED, index)
            free_value = _table_int(free, CISCO_MEMORY_POOL_FREE, index)
            if used_value is None or free_value is None:
                continue
            return MemoryData(
                index=index,
                name=_text(value),
                used_bytes=used_value,
                free_bytes=free_value,
                largest_free_bytes=_table_int(
                    largest_free, CISCO_MEMORY_POOL_LARGEST_FREE, index
                ),
            )
        return None

    @staticmethod
    def _find_fru_status(table, base, names):
        result = {}
        for oid, value in table.items():
            idx = int(_suffix(oid, base))
            name = names.get(f"{ENT_PHYSICAL_NAME}.{idx}")
            result[idx] = FruStatusData(
                idx,
                _text(name) if name is not None else f"Entity {idx}",
                int(value),
            )
        return result

    @staticmethod
    def _find_temperatures(types, scales, precisions, values, statuses, update_rates, names):
        sensors = {}
        for oid, typ in types.items():
            if int(typ) != CISCO_ENTITY_SENSOR_TYPE_CELSIUS:
                continue
            idx = int(_suffix(oid, CISCO_ENTITY_SENSOR_TYPE))
            scale = scales.get(f"{CISCO_ENTITY_SENSOR_SCALE}.{idx}")
            precision = precisions.get(f"{CISCO_ENTITY_SENSOR_PRECISION}.{idx}")
            raw = values.get(f"{CISCO_ENTITY_SENSOR_VALUE}.{idx}")
            status = statuses.get(f"{CISCO_ENTITY_SENSOR_STATUS}.{idx}")
            if scale is None or precision is None or raw is None or status is None:
                continue
            exponent = CISCO_ENTITY_SENSOR_SCALE_EXPONENT.get(int(scale))
            if exponent is None:
                continue
            name = names.get(f"{ENT_PHYSICAL_NAME}.{idx}")
            rate = update_rates.get(f"{CISCO_ENTITY_SENSOR_UPDATE_RATE}.{idx}")
            sensors[idx] = TemperatureSensorData(
                idx,
                _text(name) if name is not None else f"Temperature {idx}",
                int(raw) * (10 ** (exponent - int(precision))),
                int(status),
                int(rate) if rate is not None else None,
            )
        return sensors

    @staticmethod
    def _find_chassis(classes, names, models, serials, software):
        candidates = []
        for oid, value in classes.items():
            if int(value) != ENT_PHYSICAL_CLASS_CHASSIS:
                continue
            idx = int(_suffix(oid, ENT_PHYSICAL_CLASS))
            candidates.append(
                ChassisData(
                    idx,
                    _text(names.get(f"{ENT_PHYSICAL_NAME}.{idx}", "")),
                    _text(models.get(f"{ENT_PHYSICAL_MODEL_NAME}.{idx}", "")),
                    _text(serials.get(f"{ENT_PHYSICAL_SERIAL_NUM}.{idx}", "")),
                    _text(software.get(f"{ENT_PHYSICAL_SOFTWARE_REV}.{idx}", "")),
                )
            )
        return (
            sorted(candidates, key=lambda item: (not bool(item.serial.strip()), item.ent_index))[0]
            if candidates
            else None
        )

    @staticmethod
    def _correlate_fdb_and_arp(interfaces, bridge, fdb, arp):
        bridge_map = {
            int(_suffix(oid, DOT1D_BASE_PORT_IFINDEX)): int(value)
            for oid, value in bridge.items()
        }
        mac_to_interface = {}
        for oid, value in fdb.items():
            mac = _mac_from_fdb_suffix(_suffix(oid, DOT1D_TP_FDB_PORT))
            idx = bridge_map.get(int(value))
            if mac is not None and idx in interfaces:
                mac_to_interface[mac] = idx
        mac_to_ips = {}
        for oid, value in arp.items():
            mac = _mac_from_value(value)
            parts = _suffix(oid, IP_NET_TO_MEDIA_PHYS_ADDRESS).split(".")
            if mac is None or len(parts) < 5:
                continue
            try:
                ip = str(ipaddress.IPv4Address(".".join(parts[-4:])))
            except ipaddress.AddressValueError:
                continue
            mac_to_ips.setdefault(mac, set()).add(ip)
        for mac, idx in mac_to_interface.items():
            interfaces[idx].mac_addresses.append(mac)
            interfaces[idx].ip_addresses.extend(mac_to_ips.get(mac, ()))
        for interface in interfaces.values():
            interface.mac_addresses.sort()
            interface.ip_addresses[:] = sorted(
                set(interface.ip_addresses), key=ipaddress.ip_address
            )

    @staticmethod
    def _correlate_cdp(interfaces, addresses, ids, ports, platforms):
        rows = {
            _suffix(oid, base)
            for base, table in (
                (CDP_CACHE_ADDRESS, addresses),
                (CDP_CACHE_DEVICE_ID, ids),
                (CDP_CACHE_DEVICE_PORT, ports),
                (CDP_CACHE_PLATFORM, platforms),
            )
            for oid in table
        }
        for row in rows:
            try:
                idx = int(row.split(".", 1)[0])
            except ValueError:
                continue
            interface = interfaces.get(idx)
            if interface is None:
                continue
            address_value = addresses.get(f"{CDP_CACHE_ADDRESS}.{row}")
            interface.cdp_neighbors.append(
                CdpNeighbor(
                    _text(ids.get(f"{CDP_CACHE_DEVICE_ID}.{row}", "")),
                    _ipv4_from_value(address_value) if address_value is not None else None,
                    _text(ports.get(f"{CDP_CACHE_DEVICE_PORT}.{row}", "")),
                    _text(platforms.get(f"{CDP_CACHE_PLATFORM}.{row}", "")),
                )
            )
        for interface in interfaces.values():
            interface.cdp_neighbors.sort(key=lambda item: (item.device_id, item.port_id))

    @staticmethod
    def _correlate_lldp(
        interfaces,
        local_ids,
        local_descs,
        chassis_ids,
        port_ids,
        port_descs,
        sys_names,
    ):
        name_to_index = {item.name: idx for idx, item in interfaces.items()}
        local_port_to_ifindex: dict[str, int] = {}
        local_rows = {
            _suffix(oid, base)
            for base, table in (
                (LLDP_LOC_PORT_ID, local_ids),
                (LLDP_LOC_PORT_DESC, local_descs),
            )
            for oid in table
        }
        for local_port in local_rows:
            candidates = (
                local_ids.get(f"{LLDP_LOC_PORT_ID}.{local_port}"),
                local_descs.get(f"{LLDP_LOC_PORT_DESC}.{local_port}"),
            )
            for candidate in candidates:
                if candidate is None:
                    continue
                idx = name_to_index.get(_canonical_interface_name(_text(candidate)))
                if idx is not None:
                    local_port_to_ifindex[local_port] = idx
                    break

        rows = {
            _suffix(oid, base)
            for base, table in (
                (LLDP_REM_CHASSIS_ID, chassis_ids),
                (LLDP_REM_PORT_ID, port_ids),
                (LLDP_REM_PORT_DESC, port_descs),
                (LLDP_REM_SYS_NAME, sys_names),
            )
            for oid in table
        }
        for row in rows:
            parts = row.split(".")
            if len(parts) < 3:
                continue
            interface = interfaces.get(local_port_to_ifindex.get(parts[1], -1))
            if interface is None:
                continue
            interface.lldp_neighbors.append(
                LldpNeighbor(
                    system_name=_text(sys_names.get(f"{LLDP_REM_SYS_NAME}.{row}", "")),
                    chassis_id=_text(
                        chassis_ids.get(f"{LLDP_REM_CHASSIS_ID}.{row}", "")
                    ),
                    port_id=_text(port_ids.get(f"{LLDP_REM_PORT_ID}.{row}", "")),
                    port_description=_text(
                        port_descs.get(f"{LLDP_REM_PORT_DESC}.{row}", "")
                    ),
                )
            )
        for interface in interfaces.values():
            interface.lldp_neighbors.sort(
                key=lambda item: (item.system_name, item.chassis_id, item.port_id)
            )
