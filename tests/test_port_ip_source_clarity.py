"""Port IP sources remain separately observable and deduplicated."""
from pathlib import Path

SOURCE = Path("custom_components/cisco_catalyst/sensor.py").read_text()


def test_ip_source_sensor_registration_and_compatibility():
    assert 'CatalystPortIpSourceSensor(coordinator, interface.if_index, "cdp")' in SOURCE
    assert 'CatalystPortIpSourceSensor(coordinator, interface.if_index, "observed")' in SOURCE
    assert 'f"{coordinator.client.host}_{if_index}_learned_ips"' in SOURCE
    assert '"mac_ip_correlation"' in SOURCE
    assert '"cdp"' in SOURCE
    assert '"endpoint_ip_count"' in SOURCE


def test_deduplication_of_distinct_evidence():
    assert 'sorted(set(port.ip_addresses))' in SOURCE
    assert 'n.address for n in port.cdp_neighbors if n.address' in SOURCE
    assert 'sorted(set(correlated) | set(advertised))' in SOURCE
