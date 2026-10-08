"""Conservative MAC movement tracking for Cisco Catalyst."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import CatalystData, InterfaceData

EVENT_MAC_MOVEMENT = "cisco_catalyst_mac_movement"
EVENT_MAC_ANOMALY = "cisco_catalyst_mac_anomaly"

_CONFIRM_POLLS = 2
_ANOMALY_WINDOW = timedelta(minutes=5)
_ANOMALY_THRESHOLD = 3
_MAX_RECENT_MOVEMENTS = 20
_MAX_RECENT_ANOMALIES = 10


@dataclass(frozen=True)
class MacMovement:
    """A confirmed change in the switch port through which a MAC is observed."""

    mac: str
    old_if_index: int
    new_if_index: int
    old_interface: str
    new_interface: str
    old_path_type: str
    new_path_type: str
    observed_at: datetime
    edge_move_count: int
    anomaly: bool

    def as_event_data(self, switch_host: str) -> dict[str, Any]:
        """Return stable event payload data."""
        return {
            "switch_host": switch_host,
            "mac": self.mac,
            "old_if_index": self.old_if_index,
            "new_if_index": self.new_if_index,
            "old_interface": self.old_interface,
            "new_interface": self.new_interface,
            "old_path_type": self.old_path_type,
            "new_path_type": self.new_path_type,
            "observed_at": self.observed_at.isoformat(),
            "edge_move_count": self.edge_move_count,
            "anomaly": self.anomaly,
        }


class MacMovementTracker:
    """Track confirmed MAC path changes without claiming direct attachment."""

    def __init__(self, hass: HomeAssistant, switch_host: str) -> None:
        self.hass = hass
        self.switch_host = switch_host
        self._confirmed: dict[str, int] = {}
        self._candidates: dict[str, tuple[int, int]] = {}
        self._edge_history: dict[str, deque[datetime]] = defaultdict(deque)
        self.anomaly_count = 0
        self.recent_movements: deque[dict[str, Any]] = deque(maxlen=_MAX_RECENT_MOVEMENTS)
        self.recent_anomalies: deque[dict[str, Any]] = deque(maxlen=_MAX_RECENT_ANOMALIES)

    @staticmethod
    def classify_path(interface: InterfaceData) -> str:
        """Classify only from explicit switch facts, never model/name heuristics."""
        if interface.is_trunk is True or interface.cdp_neighbors or interface.lldp_neighbors:
            return "infrastructure"
        if interface.is_trunk is False and len(interface.mac_addresses) > 1:
            # Multiple learned MACs on an explicitly non-trunk port are evidence of
            # a downstream path (for example an AP, unmanaged switch, phone/PC, or
            # bridge). Treat it as infrastructure for anomaly suppression without
            # claiming what device type is actually connected.
            return "infrastructure"
        if interface.is_trunk is False and len(interface.mac_addresses) <= 1:
            return "edge"
        return "unknown"

    def observe(self, data: CatalystData, *, now: datetime | None = None) -> list[MacMovement]:
        """Observe one authoritative coordinator snapshot and return confirmed moves."""
        observed_at = now or datetime.now(timezone.utc)

        # Do not pick an arbitrary port if the same MAC is simultaneously visible
        # through multiple physical interfaces in one snapshot. That can happen
        # transiently while switch tables converge and is not enough evidence of a
        # real movement.
        observed_ports: dict[str, set[int]] = defaultdict(set)
        for if_index, interface in data.interfaces.items():
            for mac in interface.mac_addresses:
                observed_ports[mac].add(if_index)
        current = {
            mac: next(iter(if_indexes))
            for mac, if_indexes in observed_ports.items()
            if len(if_indexes) == 1
        }
        for mac, if_indexes in observed_ports.items():
            if len(if_indexes) > 1:
                self._candidates.pop(mac, None)

        movements: list[MacMovement] = []
        for mac, new_if_index in current.items():
            old_if_index = self._confirmed.get(mac)
            if old_if_index is None:
                # First sighting establishes a baseline and never raises an event.
                self._confirmed[mac] = new_if_index
                self._candidates.pop(mac, None)
                continue

            if new_if_index == old_if_index:
                self._candidates.pop(mac, None)
                continue

            candidate_if_index, count = self._candidates.get(mac, (new_if_index, 0))
            if candidate_if_index != new_if_index:
                candidate_if_index, count = new_if_index, 0
            count += 1
            self._candidates[mac] = (candidate_if_index, count)
            if count < _CONFIRM_POLLS:
                continue

            old_interface = data.interfaces.get(old_if_index)
            new_interface = data.interfaces.get(new_if_index)
            if old_interface is None or new_interface is None:
                # A missing interface means topology is incomplete; accept the new
                # baseline but do not invent movement semantics.
                self._confirmed[mac] = new_if_index
                self._candidates.pop(mac, None)
                continue

            old_type = self.classify_path(old_interface)
            new_type = self.classify_path(new_interface)
            edge_move_count = 0
            anomaly = False
            history = self._edge_history[mac]
            cutoff = observed_at - _ANOMALY_WINDOW
            while history and history[0] < cutoff:
                history.popleft()

            if old_type == "edge" and new_type == "edge":
                history.append(observed_at)
                edge_move_count = len(history)
                anomaly = edge_move_count >= _ANOMALY_THRESHOLD
            else:
                # Crossing infrastructure/unknown paths is expected often enough
                # that it must not contribute to an edge-flap alarm sequence.
                history.clear()

            movement = MacMovement(
                mac=mac,
                old_if_index=old_if_index,
                new_if_index=new_if_index,
                old_interface=old_interface.name,
                new_interface=new_interface.name,
                old_path_type=old_type,
                new_path_type=new_type,
                observed_at=observed_at,
                edge_move_count=edge_move_count,
                anomaly=anomaly,
            )
            movements.append(movement)
            event_data = movement.as_event_data(self.switch_host)
            self.recent_movements.append(event_data)
            self.hass.bus.async_fire(EVENT_MAC_MOVEMENT, event_data)
            if anomaly:
                self.anomaly_count += 1
                self.recent_anomalies.append(event_data)
                self.hass.bus.async_fire(EVENT_MAC_ANOMALY, event_data)

            self._confirmed[mac] = new_if_index
            self._candidates.pop(mac, None)

        # MACs absent from an FDB snapshot deliberately keep their last confirmed
        # location. Aging/disappearance alone is not movement and must not alarm.
        return movements
