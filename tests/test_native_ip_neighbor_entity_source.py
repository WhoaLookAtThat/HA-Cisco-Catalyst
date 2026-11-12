"""Contracts for per-port native discovery diagnostics."""
from pathlib import Path

SOURCE = Path("custom_components/cisco_catalyst/sensor.py").read_text(encoding="utf-8")


def test_entities_registered_per_port():
    assert "CatalystLearnedIpSensor(coordinator, interface.if_index)" in SOURCE
    assert "CatalystNeighborDiscoverySensor(coordinator, interface.if_index)" in SOURCE


def test_discovery_attributes_bounded_and_serializable():
    assert "_PORT_DIAGNOSTIC_MAX_IPS" in SOURCE
    assert '"ip_addresses_truncated"' in SOURCE
    assert '"neighbors_truncated"' in SOURCE
    assert "asdict(n) for n in port.cdp_neighbors" in SOURCE
    assert "asdict(n) for n in port.lldp_neighbors" in SOURCE


def test_no_switch_writes_in_new_sensors():
    chunk = SOURCE.split("class CatalystLearnedIpSensor(", 1)[1].split("class CatalystErrorSensor(", 1)[0]
    assert "async_set_" not in chunk
    assert "async_turn_" not in chunk
