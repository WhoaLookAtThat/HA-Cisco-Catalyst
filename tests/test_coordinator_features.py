"""Tests for normalized VLAN and LLDP coordinator data."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.cisco_catalyst.coordinator import (
    CatalystCoordinator,
    InterfaceData,
    _decode_vlan_bitmap,
    _operational_vlan_ids,
)
from custom_components.cisco_catalyst.snmp import CatalystSnmpError
from custom_components.cisco_catalyst.const import (
    CISCO_VTP_VLAN_STATE,
    LLDP_LOC_PORT_DESC,
    LLDP_LOC_PORT_ID,
    LLDP_REM_CHASSIS_ID,
    LLDP_REM_PORT_DESC,
    LLDP_REM_PORT_ID,
    LLDP_REM_SYS_NAME,
)


class PrettyValue:
    def __init__(self, value: str) -> None:
        self.value = value

    def prettyPrint(self) -> str:
        return self.value


def test_decode_vlan_bitmap_uses_most_significant_bit_first() -> None:
    assert _decode_vlan_bitmap(bytes([0b01000001]), 1024) == [1025, 1031]


def test_decode_vlan_bitmap_omits_reserved_vlan_zero() -> None:
    assert _decode_vlan_bitmap(bytes([0b11000000])) == [1]


def test_correlate_lldp_maps_local_port_name_to_ifindex() -> None:
    interfaces = {
        8: InterfaceData(if_index=8, name="GigabitEthernet1/0/1"),
    }
    local_ids = {f"{LLDP_LOC_PORT_ID}.1": PrettyValue("Gi1/0/1")}
    local_descs = {f"{LLDP_LOC_PORT_DESC}.1": PrettyValue("Gi1/0/1")}
    row = "123.1.7"

    CatalystCoordinator._correlate_lldp(
        interfaces,
        local_ids,
        local_descs,
        {f"{LLDP_REM_CHASSIS_ID}.{row}": PrettyValue("0011.2233.4455")},
        {f"{LLDP_REM_PORT_ID}.{row}": PrettyValue("eth0")},
        {f"{LLDP_REM_PORT_DESC}.{row}": PrettyValue("uplink")},
        {f"{LLDP_REM_SYS_NAME}.{row}": PrettyValue("neighbor")},
    )

    assert len(interfaces[8].lldp_neighbors) == 1
    neighbor = interfaces[8].lldp_neighbors[0]
    assert neighbor.system_name == "neighbor"
    assert neighbor.port_id == "eth0"


@pytest.mark.asyncio
async def test_optional_walk_omits_unavailable_mib() -> None:
    """An unsupported optional MIB must not fail the coordinator update."""
    coordinator = object.__new__(CatalystCoordinator)
    coordinator.client = SimpleNamespace(walk=AsyncMock(side_effect=CatalystSnmpError("noSuchName")))
    coordinator._static_walk_cache = {}

    assert await coordinator._walk_optional("1.2.3") == {}


def test_access_port_does_not_need_trunk_vlan_bitmap() -> None:
    """Access ports keep their access VLAN without retaining trunk bitmap data."""
    interface = InterfaceData(
        if_index=14,
        name="GigabitEthernet1/0/7",
        access_vlan=1,
        is_trunk=False,
        native_vlan=None,
        allowed_vlans=[],
    )
    assert interface.access_vlan == 1
    assert interface.is_trunk is False
    assert interface.native_vlan is None
    assert interface.allowed_vlans == []


def test_operational_vlan_ids_parses_domain_vlan_index_and_state() -> None:
    table = {
        f"{CISCO_VTP_VLAN_STATE}.1.1": 1,
        f"{CISCO_VTP_VLAN_STATE}.1.20": 1,
        f"{CISCO_VTP_VLAN_STATE}.1.30": 2,
        f"{CISCO_VTP_VLAN_STATE}.2.40": 1,
        f"{CISCO_VTP_VLAN_STATE}.bad": "bad",
    }

    assert _operational_vlan_ids(table) == {1, 20, 40}
