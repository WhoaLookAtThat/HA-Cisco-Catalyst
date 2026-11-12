"""Source contracts for discoverable native Home Assistant port diagnostics."""
from pathlib import Path

SOURCE = Path("custom_components/cisco_catalyst/sensor.py").read_text()


def test_primary_mac_sensor_registered_and_ambiguous_is_not_guessed():
    assert "CatalystPrimaryMacSensor(coordinator, interface.if_index)" in SOURCE
    assert 'len(port.mac_addresses) != 1' in SOURCE
    assert 'return port.mac_addresses[0]' in SOURCE
    assert '"ambiguous": bool(port and len(port.mac_addresses) > 1)' in SOURCE


def test_poe_detail_sensors_registered_and_have_watt_units():
    assert 'for field in ("allocated", "available", "maximum")' in SOURCE
    assert '"power_allocated_mw"' in SOURCE
    assert '"power_available_mw"' in SOURCE
    assert '"max_power_drawn_mw"' in SOURCE
    assert "UnitOfPower.WATT" in SOURCE
    assert "milliwatts / 1000" in SOURCE
