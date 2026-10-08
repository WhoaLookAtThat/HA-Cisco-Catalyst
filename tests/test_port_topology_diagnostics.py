"""Tests for native Home Assistant port topology diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from homeassistant.helpers.entity import EntityCategory

from custom_components.cisco_catalyst.coordinator import (
    CatalystData,
    CdpNeighbor,
    InterfaceData,
    LldpNeighbor,
)
from custom_components.cisco_catalyst.sensor import (
    CatalystLearnedMacSensor,
    CatalystPortNetworkSensor,
)


def _coordinator(interface: InterfaceData) -> Any:
    return SimpleNamespace(
        data=CatalystData(
            sys_name="test-switch",
            sys_descr="Cisco IOS",
            uptime_ticks=100,
            interfaces={interface.if_index: interface},
            poe_ports={},
        ),
        client=SimpleNamespace(host="192.0.2.1"),
        last_update_success=True,
    )


def test_network_mode_sensor_exposes_access_vlan_and_neighbor_status() -> None:
    interface = InterfaceData(
        if_index=1,
        name="GigabitEthernet1/0/1",
        is_trunk=False,
        access_vlan=20,
        cdp_neighbors=[CdpNeighbor(device_id="phone")],
    )
    sensor = CatalystPortNetworkSensor(_coordinator(interface), 1)

    assert sensor.native_value == "access"
    assert sensor.entity_category is EntityCategory.DIAGNOSTIC
    assert sensor.extra_state_attributes == {
        "cisco_catalyst_role": "network_mode",
        "interface_id": "192.0.2.1:interface:1",
        "interface_name": "GigabitEthernet1/0/1",
        "is_physical": True,
        "if_index": 1,
        "physical_group": "primary",
        "physical_member": 1,
        "physical_slot": 0,
        "physical_port": 1,
        "physical_position": 1,
        "member": 1,
        "slot": 0,
        "port": 1,
        "cdp_neighbor_count": 1,
        "lldp_neighbor_count": 0,
        "neighbor_discovered": True,
        "access_vlan": 20,
    }


def test_network_mode_sensor_exposes_trunk_native_and_allowed_vlans() -> None:
    interface = InterfaceData(
        if_index=2,
        name="GigabitEthernet1/0/2",
        is_trunk=True,
        native_vlan=99,
        allowed_vlans=[10, 20, 99],
        lldp_neighbors=[LldpNeighbor(system_name="ap-1")],
    )
    sensor = CatalystPortNetworkSensor(_coordinator(interface), 2)

    assert sensor.native_value == "trunk"
    assert sensor.extra_state_attributes["native_vlan"] == 99
    assert sensor.extra_state_attributes["allowed_vlans_count"] == 3
    assert sensor.extra_state_attributes["allowed_vlans"] == [10, 20, 99]
    assert sensor.extra_state_attributes["allowed_vlans_truncated"] is False
    assert sensor.extra_state_attributes["lldp_neighbor_count"] == 1
    assert sensor.extra_state_attributes["neighbor_discovered"] is True
    assert sensor._unrecorded_attributes == frozenset({"allowed_vlans"})


def test_network_mode_sensor_omits_unsupported_vlan_attributes() -> None:
    interface = InterfaceData(
        if_index=3,
        name="GigabitEthernet1/0/3",
    )
    sensor = CatalystPortNetworkSensor(_coordinator(interface), 3)

    assert sensor.native_value == "unknown"
    attributes = sensor.extra_state_attributes
    assert "access_vlan" not in attributes
    assert "native_vlan" not in attributes
    assert "allowed_vlans" not in attributes
    assert attributes["cdp_neighbor_count"] == 0
    assert attributes["lldp_neighbor_count"] == 0
    assert attributes["neighbor_discovered"] is False


def test_network_mode_sensor_bounds_allowed_vlan_attribute() -> None:
    interface = InterfaceData(
        if_index=6,
        name="GigabitEthernet1/0/6",
        is_trunk=True,
        allowed_vlans=list(range(1, 201)),
    )
    sensor = CatalystPortNetworkSensor(_coordinator(interface), 6)
    attributes = sensor.extra_state_attributes

    assert attributes["allowed_vlans_count"] == 200
    assert len(attributes["allowed_vlans"]) == 128
    assert attributes["allowed_vlans_truncated"] is True


def test_learned_mac_sensor_uses_count_as_state_and_unrecorded_lists() -> None:
    interface = InterfaceData(
        if_index=4,
        name="GigabitEthernet1/0/4",
        mac_addresses=["00:11:22:33:44:55", "00:11:22:33:44:66"],
        ip_addresses=["192.0.2.10"],
    )
    sensor = CatalystLearnedMacSensor(_coordinator(interface), 4)

    assert sensor.native_value == 2
    assert sensor.entity_category is EntityCategory.DIAGNOSTIC
    assert sensor.extra_state_attributes["mac_addresses"] == [
        "00:11:22:33:44:55",
        "00:11:22:33:44:66",
    ]
    assert sensor.extra_state_attributes["mac_addresses_truncated"] is False
    assert sensor.extra_state_attributes["learned_ip_count"] == 1
    assert sensor.extra_state_attributes["ip_addresses"] == ["192.0.2.10"]
    assert sensor.extra_state_attributes["ip_addresses_truncated"] is False
    assert sensor._unrecorded_attributes == frozenset(
        {"mac_addresses", "ip_addresses"}
    )


def test_learned_mac_sensor_bounds_current_address_attributes() -> None:
    mac_addresses = [f"00:11:22:33:{index // 256:02x}:{index % 256:02x}" for index in range(80)]
    ip_addresses = [f"192.0.2.{index}" for index in range(1, 70)]
    interface = InterfaceData(
        if_index=7,
        name="GigabitEthernet1/0/7",
        mac_addresses=mac_addresses,
        ip_addresses=ip_addresses,
    )
    sensor = CatalystLearnedMacSensor(_coordinator(interface), 7)
    attributes = sensor.extra_state_attributes

    assert sensor.native_value == 80
    assert len(attributes["mac_addresses"]) == 64
    assert attributes["mac_addresses_truncated"] is True
    assert attributes["learned_ip_count"] == 69
    assert len(attributes["ip_addresses"]) == 64
    assert attributes["ip_addresses_truncated"] is True


def test_learned_mac_sensor_zero_state_omits_empty_address_lists() -> None:
    interface = InterfaceData(
        if_index=5,
        name="GigabitEthernet1/0/5",
    )
    sensor = CatalystLearnedMacSensor(_coordinator(interface), 5)

    assert sensor.native_value == 0
    attributes = sensor.extra_state_attributes
    assert "mac_addresses" not in attributes
    assert "ip_addresses" not in attributes
    assert sensor.device_info["identifiers"] == {
        ("cisco_catalyst", "192.0.2.1:interface:5")
    }
