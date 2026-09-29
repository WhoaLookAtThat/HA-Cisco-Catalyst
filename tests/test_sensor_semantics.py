"""Regression tests for sensor semantics validated on the Catalyst 3650."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from homeassistant.components.sensor import SensorStateClass

from custom_components.cisco_catalyst.coordinator import (
    CatalystData,
    FruStatusData,
    InterfaceData,
)
from custom_components.cisco_catalyst.sensor import (
    CatalystCounterSensor,
    CatalystFruStatusSensor,
    CatalystSpeedSensor,
    CatalystUptimeSensor,
)


def _coordinator(data: CatalystData) -> Any:
    return SimpleNamespace(
        data=data,
        client=SimpleNamespace(host="192.0.2.1"),
        last_update_success=True,
    )


def _data(*, oper_status: int = 1, speed_mbps: int = 1000, admin_status: int | None = 1) -> CatalystData:
    return CatalystData(
        sys_name="test-switch",
        sys_descr="Cisco IOS",
        uptime_ticks=4_669_996,
        interfaces={
            1: InterfaceData(
                if_index=1,
                name="GigabitEthernet1/0/1",
                oper_status=oper_status,
                admin_status=admin_status,
                speed_mbps=speed_mbps,
                in_octets=12_967_977_902,
                out_octets=17_556_163_198,
            )
        },
        poe_ports={},
        power_supplies={
            10: FruStatusData(
                ent_index=10,
                name="Switch 1 - Power Supply B",
                status=1,
            )
        },
    )


def test_counter_keeps_exact_byte_semantics() -> None:
    sensor = CatalystCounterSensor(_coordinator(_data()), 1, "tx")
    assert sensor.native_value == 17_556_163_198
    assert sensor.native_unit_of_measurement == "B"
    assert sensor.state_class is SensorStateClass.TOTAL_INCREASING
    assert sensor.device_class is None


def test_speed_explains_when_link_is_down() -> None:
    sensor = CatalystSpeedSensor(_coordinator(_data(oper_status=2)), 1)
    assert sensor.native_value == "N/A (port down)"


def test_speed_explains_when_port_is_disabled() -> None:
    sensor = CatalystSpeedSensor(_coordinator(_data(oper_status=2, admin_status=2)), 1)
    assert sensor.native_value == "N/A (port disabled)"


def test_speed_missing_admin_status_is_not_disabled() -> None:
    sensor = CatalystSpeedSensor(_coordinator(_data(admin_status=None)), 1)
    assert sensor.native_value == "1G"


def test_speed_reported_when_link_is_up() -> None:
    sensor = CatalystSpeedSensor(_coordinator(_data()), 1)
    assert sensor.native_value == "1G"
    assert sensor.native_unit_of_measurement is None


def test_speed_formats_current_catalyst_rates() -> None:
    expected = {
        10: "10M",
        100: "100M",
        1000: "1G",
        2500: "2.5G",
        5000: "5G",
        10000: "10G",
        25000: "25G",
        40000: "40G",
        50000: "50G",
        100000: "100G",
        200000: "200G",
        400000: "400G",
    }
    for speed_mbps, label in expected.items():
        sensor = CatalystSpeedSensor(_coordinator(_data(speed_mbps=speed_mbps)), 1)
        assert sensor.native_value == label


def test_uptime_remains_native_seconds() -> None:
    sensor = CatalystUptimeSensor(_coordinator(_data()))
    assert sensor.native_value == 46_699.96
    assert sensor.native_unit_of_measurement == "s"


def test_fru_status_is_human_readable() -> None:
    sensor = CatalystFruStatusSensor(_coordinator(_data()), 10, "power")
    assert sensor.native_value == "Off (environment/other)"


def test_interface_entities_attach_to_child_port_device() -> None:
    coordinator = _coordinator(_data())
    sensor = CatalystSpeedSensor(coordinator, 1)
    info = sensor.device_info
    assert info["identifiers"] == {
        ("cisco_catalyst", "192.0.2.1:interface:1")
    }
    assert info["via_device"] == ("cisco_catalyst", "192.0.2.1")
    assert info["name"] == "GigabitEthernet1/0/1"
