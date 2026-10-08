"""Tests for native per-port operational/statistical diagnostics."""

from types import SimpleNamespace

from homeassistant.components.sensor import SensorStateClass

from custom_components.cisco_catalyst.sensor import (
    CatalystDiscardSensor,
    CatalystPoePortPowerSensor,
)


def _coordinator():
    interface = SimpleNamespace(
        name="GigabitEthernet1/0/38",
        in_discards=7,
        out_discards=9,
    )
    poe = SimpleNamespace(
        index="1.38",
        name="GigabitEthernet1/0/38",
        enabled=True,
        device_detected=True,
        power_consumption_mw=2200,
        power_allocated_mw=15400,
        power_available_mw=30000,
        max_power_drawn_mw=4100,
    )
    return SimpleNamespace(
        client=SimpleNamespace(host="192.0.2.1"),
        data=SimpleNamespace(
            interfaces={38: interface},
            poe_ports={"1.38": poe},
        ),
        last_update_success=True,
    )


def test_discard_sensors_are_native_child_device_entities() -> None:
    coordinator = _coordinator()
    rx = CatalystDiscardSensor(coordinator, 38, "rx")
    tx = CatalystDiscardSensor(coordinator, 38, "tx")

    assert rx.native_value == 7
    assert tx.native_value == 9
    assert rx.native_unit_of_measurement == "packets"
    assert rx.state_class is SensorStateClass.TOTAL_INCREASING
    assert rx.extra_state_attributes == {}
    assert rx.device_info["identifiers"] == {
        ("cisco_catalyst", "192.0.2.1:interface:38")
    }


def test_poe_power_sensor_exposes_first_class_power_and_bounded_details() -> None:
    coordinator = _coordinator()
    sensor = CatalystPoePortPowerSensor(coordinator, "1.38")

    assert sensor.native_value == 2.2
    assert sensor.extra_state_attributes == {
        "poe_enabled": True,
        "powered_device_detected": True,
        "allocated_power_w": 15.4,
        "available_power_w": 30.0,
        "max_power_drawn_w": 4.1,
    }
    assert sensor.device_info["identifiers"] == {
        ("cisco_catalyst", "192.0.2.1:interface:38")
    }
