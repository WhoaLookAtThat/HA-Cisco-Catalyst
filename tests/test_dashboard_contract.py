"""Tests for the frontend-visible dashboard contract."""

from custom_components.cisco_catalyst.entity import (
    _interface_contract_attributes,
    _physical_layout,
)
from custom_components.cisco_catalyst.sensor import (
    CatalystCounterSensor,
    CatalystDashboardContractSensor,
)


def test_front_panel_layout_metadata() -> None:
    assert _physical_layout("GigabitEthernet1/0/24") == {
        "physical_group": "primary",
        "physical_member": 1,
        "physical_slot": 0,
        "physical_port": 24,
        "physical_position": 24,
        "member": 1,
        "slot": 0,
        "port": 24,
    }


def test_module_layout_metadata() -> None:
    assert _physical_layout("GigabitEthernet1/1/4") == {
        "physical_group": "additional",
        "physical_member": 1,
        "physical_slot": 1,
        "physical_port": 4,
        "physical_position": 4,
        "member": 1,
        "slot": 1,
        "port": 4,
    }


def test_unknown_layout_metadata_is_explicit() -> None:
    assert _physical_layout("Port-channel1") == {
        "physical_group": "unknown",
        "physical_position": None,
        "physical_member": None,
        "physical_slot": None,
        "physical_port": None,
        "member": None,
        "slot": None,
        "port": None,
    }


def test_interface_contract_is_independent_of_display_names() -> None:
    assert _interface_contract_attributes(
        "192.0.2.10", 8, "GigabitEthernet1/0/1", "link"
    ) == {
        "cisco_catalyst_role": "link",
        "interface_id": "192.0.2.10:interface:8",
        "interface_name": "GigabitEthernet1/0/1",
        "is_physical": True,
        "if_index": 8,
        "physical_group": "primary",
        "physical_member": 1,
        "physical_slot": 0,
        "physical_port": 1,
        "physical_position": 1,
        "member": 1,
        "slot": 0,
        "port": 1,
    }


def test_counter_roles_use_contract_names() -> None:
    class Coordinator:
        client = type("Client", (), {"host": "192.0.2.1"})()
        data = type(
            "Data",
            (),
            {
                "interfaces": {
                    8: type(
                        "Interface",
                        (),
                        {"name": "GigabitEthernet1/0/1"},
                    )()
                }
            },
        )()

    rx = CatalystCounterSensor(Coordinator(), 8, "rx")
    tx = CatalystCounterSensor(Coordinator(), 8, "tx")
    assert rx.catalyst_role == "rx_bytes"
    assert tx.catalyst_role == "tx_bytes"


def test_parent_switch_advertises_contract_v1() -> None:
    class Coordinator:
        client = type("Client", (), {"host": "192.0.2.1"})()

    entity = CatalystDashboardContractSensor(Coordinator())
    assert entity.native_value == 1
    assert entity.extra_state_attributes == {
        "cisco_catalyst_role": "switch",
        "dashboard_contract_version": 1,
        "is_cisco_catalyst_switch": True,
    }
