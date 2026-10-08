"""Tests for the parent SNMP status diagnostic sensor."""

from types import SimpleNamespace

from custom_components.cisco_catalyst.sensor import CatalystSnmpStatusSensor


def _coordinator(version: str, *, enabled: bool, port: int):
    return SimpleNamespace(
        client=SimpleNamespace(host="192.0.2.1", version=version),
        last_update_success=True,
        snmp_mode="3 (authPriv)" if version == "3" else "2c",
        notification_listener_enabled=enabled,
        notification_listener_port=port,
    )


def test_snmp_status_exposes_mode_and_listener_without_secrets() -> None:
    sensor = CatalystSnmpStatusSensor(_coordinator("3", enabled=True, port=1162))
    assert sensor.native_value == "3 (authPriv)"
    assert sensor.extra_state_attributes == {
        "notification_listener": "enabled",
        "notification_listener_port": 1162,
        "notification_listener_transport": "UDP",
    }


def test_snmp_status_reports_disabled_listener() -> None:
    sensor = CatalystSnmpStatusSensor(_coordinator("2c", enabled=False, port=2162))
    assert sensor.native_value == "2c"
    assert sensor.extra_state_attributes["notification_listener"] == "disabled"
    assert sensor.extra_state_attributes["notification_listener_port"] == 2162
