"""Tests for conservative topology-aware MAC movement tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.cisco_catalyst.coordinator import CatalystData, InterfaceData
from custom_components.cisco_catalyst.mac_movement import (
    EVENT_MAC_ANOMALY,
    EVENT_MAC_MOVEMENT,
    MacMovementTracker,
)


def _data(*interfaces: InterfaceData) -> CatalystData:
    return CatalystData(
        sys_name="switch",
        sys_descr="test",
        uptime_ticks=1,
        interfaces={item.if_index: item for item in interfaces},
        poe_ports={},
    )


def _port(index: int, macs: list[str], *, trunk: bool | None = False, neighbor: bool = False) -> InterfaceData:
    interface = InterfaceData(
        if_index=index,
        name=f"GigabitEthernet1/0/{index}",
        is_trunk=trunk,
        mac_addresses=macs,
    )
    if neighbor:
        interface.cdp_neighbors.append(SimpleNamespace())
    return interface


def _tracker() -> tuple[MacMovementTracker, MagicMock]:
    bus = MagicMock()
    hass = SimpleNamespace(bus=bus)
    return MacMovementTracker(hass, "192.0.2.10"), bus


def test_first_sighting_and_single_changed_poll_do_not_emit() -> None:
    tracker, bus = _tracker()
    mac = "00:11:22:33:44:55"

    tracker.observe(_data(_port(1, [mac]), _port(2, [])))
    tracker.observe(_data(_port(1, []), _port(2, [mac])))

    bus.async_fire.assert_not_called()


def test_move_requires_two_consecutive_observations() -> None:
    tracker, bus = _tracker()
    mac = "00:11:22:33:44:55"

    tracker.observe(_data(_port(1, [mac]), _port(2, [])))
    tracker.observe(_data(_port(1, []), _port(2, [mac])))
    movements = tracker.observe(_data(_port(1, []), _port(2, [mac])))

    assert len(movements) == 1
    assert movements[0].old_if_index == 1
    assert movements[0].new_if_index == 2
    assert movements[0].anomaly is False
    bus.async_fire.assert_called_once()
    assert bus.async_fire.call_args.args[0] == EVENT_MAC_MOVEMENT
    assert len(tracker.recent_movements) == 1
    assert tracker.recent_movements[0]["mac"] == mac
    assert tracker.recent_movements[0]["old_interface"] == "GigabitEthernet1/0/1"
    assert tracker.recent_movements[0]["new_interface"] == "GigabitEthernet1/0/2"


def test_disappearance_and_reappearance_same_port_is_not_movement() -> None:
    tracker, bus = _tracker()
    mac = "00:11:22:33:44:55"

    tracker.observe(_data(_port(1, [mac])))
    tracker.observe(_data(_port(1, [])))
    tracker.observe(_data(_port(1, [mac])))

    bus.async_fire.assert_not_called()


def test_same_mac_on_multiple_ports_is_ignored_as_ambiguous() -> None:
    tracker, bus = _tracker()
    mac = "00:11:22:33:44:55"

    tracker.observe(_data(_port(1, [mac]), _port(2, [])))
    tracker.observe(_data(_port(1, [mac]), _port(2, [mac])))
    tracker.observe(_data(_port(1, []), _port(2, [mac])))

    bus.async_fire.assert_not_called()


def test_multi_mac_access_path_is_infrastructure_not_edge() -> None:
    tracker, _bus = _tracker()
    interface = _port(1, ["00:11:22:33:44:55", "00:11:22:33:44:66"])
    assert tracker.classify_path(interface) == "infrastructure"


def test_multi_mac_path_with_unknown_trunk_state_remains_unknown() -> None:
    tracker, _bus = _tracker()
    interface = _port(
        1,
        ["00:11:22:33:44:55", "00:11:22:33:44:66"],
        trunk=None,
    )
    assert tracker.classify_path(interface) == "unknown"


def test_neighbor_marks_access_port_as_infrastructure() -> None:
    tracker, _bus = _tracker()
    interface = _port(1, ["00:11:22:33:44:55"], neighbor=True)
    assert tracker.classify_path(interface) == "infrastructure"


def test_infrastructure_path_change_does_not_build_edge_anomaly_history() -> None:
    tracker, bus = _tracker()
    mac = "00:11:22:33:44:55"
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    tracker.observe(_data(_port(1, [mac]), _port(2, [], trunk=True)), now=now)
    tracker.observe(_data(_port(1, []), _port(2, [mac], trunk=True)), now=now + timedelta(seconds=10))
    movements = tracker.observe(
        _data(_port(1, []), _port(2, [mac], trunk=True)),
        now=now + timedelta(seconds=20),
    )

    assert len(movements) == 1
    assert movements[0].new_path_type == "infrastructure"
    assert movements[0].edge_move_count == 0
    assert movements[0].anomaly is False
    assert tracker.anomaly_count == 0
    assert not any(call.args[0] == EVENT_MAC_ANOMALY for call in bus.async_fire.call_args_list)


def test_three_confirmed_edge_moves_within_window_raise_anomaly() -> None:
    tracker, bus = _tracker()
    mac = "00:11:22:33:44:55"
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def observe_location(index: int, stamp: datetime) -> None:
        other = 2 if index == 1 else 1
        snapshot = _data(_port(index, [mac]), _port(other, []))
        tracker.observe(snapshot, now=stamp)

    observe_location(1, now)
    observe_location(2, now + timedelta(seconds=10))
    observe_location(2, now + timedelta(seconds=20))
    observe_location(1, now + timedelta(seconds=30))
    observe_location(1, now + timedelta(seconds=40))
    observe_location(2, now + timedelta(seconds=50))
    movements = tracker.observe(
        _data(_port(1, []), _port(2, [mac])),
        now=now + timedelta(seconds=60),
    )

    assert len(movements) == 1
    assert movements[0].edge_move_count == 3
    assert movements[0].anomaly is True
    assert tracker.anomaly_count == 1
    assert len(tracker.recent_movements) == 3
    assert len(tracker.recent_anomalies) == 1
    anomaly_calls = [call for call in bus.async_fire.call_args_list if call.args[0] == EVENT_MAC_ANOMALY]
    assert len(anomaly_calls) == 1
    assert anomaly_calls[0].args[1]["mac"] == mac


def test_recent_movements_are_bounded() -> None:
    tracker, _bus = _tracker()
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    for suffix in range(25):
        mac = f"00:11:22:33:44:{suffix:02x}"
        tracker.observe(_data(_port(1, [mac]), _port(2, [])), now=now)
        tracker.observe(
            _data(_port(1, []), _port(2, [mac])),
            now=now + timedelta(seconds=1),
        )
        tracker.observe(
            _data(_port(1, []), _port(2, [mac])),
            now=now + timedelta(seconds=2),
        )

    assert len(tracker.recent_movements) == 20
    assert tracker.recent_movements[0]["mac"] == "00:11:22:33:44:05"
    assert tracker.recent_movements[-1]["mac"] == "00:11:22:33:44:18"


def test_edge_move_window_expires() -> None:
    tracker, _bus = _tracker()
    mac = "00:11:22:33:44:55"
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    tracker.observe(_data(_port(1, [mac]), _port(2, [])), now=now)
    tracker.observe(_data(_port(1, []), _port(2, [mac])), now=now + timedelta(seconds=10))
    tracker.observe(_data(_port(1, []), _port(2, [mac])), now=now + timedelta(seconds=20))
    tracker.observe(_data(_port(1, [mac]), _port(2, [])), now=now + timedelta(minutes=6))
    movements = tracker.observe(
        _data(_port(1, [mac]), _port(2, [])),
        now=now + timedelta(minutes=6, seconds=10),
    )

    assert len(movements) == 1
    assert movements[0].edge_move_count == 1
    assert movements[0].anomaly is False
