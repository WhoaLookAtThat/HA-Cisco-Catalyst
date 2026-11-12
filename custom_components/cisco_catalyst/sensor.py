"""Sensors for Cisco Catalyst."""

from __future__ import annotations

from typing import Any
from dataclasses import asdict
from datetime import datetime, timezone

from .protected_interface_options import get_protected_interfaces
from .vlan_preflight_freshness import assess_snapshot_freshness

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CISCO_ENTITY_SENSOR_STATUS_OK, FAN_STATUS_NAMES, FRU_POWER_STATUS_NAMES
from .coordinator import CatalystCoordinator
from .entity import CatalystEntity, CatalystInterfaceEntity, CatalystPoeEntity

_PORT_DIAGNOSTIC_MAX_MACS = 64
_PORT_DIAGNOSTIC_MAX_IPS = 64
_PORT_DIAGNOSTIC_MAX_VLANS = 128


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[CatalystCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        CatalystDashboardContractSensor(coordinator),
        CatalystSnmpStatusSensor(coordinator),
        CatalystVlanReviewReadinessSensor(coordinator, dict(entry.options)),
        CatalystUptimeSensor(coordinator),
        CatalystPoePowerSensor(coordinator),
        CatalystCpuSensor(coordinator),
        CatalystMemorySensor(coordinator),
        CatalystMacMovementAnomalySensor(coordinator),
    ]
    entities.extend(
        CatalystTemperatureSensor(coordinator, idx)
        for idx in coordinator.data.temperatures
    )
    entities.extend(
        CatalystFruStatusSensor(coordinator, idx, "power")
        for idx in coordinator.data.power_supplies
    )
    entities.extend(
        CatalystFruStatusSensor(coordinator, idx, "fan")
        for idx in coordinator.data.fans
    )
    for interface in coordinator.data.interfaces.values():
        entities.extend(
            (
                CatalystCounterSensor(coordinator, interface.if_index, "rx"),
                CatalystCounterSensor(coordinator, interface.if_index, "tx"),
                CatalystSpeedSensor(coordinator, interface.if_index),
                CatalystErrorSensor(coordinator, interface.if_index),
                CatalystDiscardSensor(coordinator, interface.if_index, "rx"),
                CatalystDiscardSensor(coordinator, interface.if_index, "tx"),
                CatalystPortNetworkSensor(coordinator, interface.if_index),
                CatalystAccessVlanStatusSensor(coordinator, interface.if_index),
                CatalystLearnedMacSensor(coordinator, interface.if_index),
                CatalystPrimaryMacSensor(coordinator, interface.if_index),
                CatalystLearnedIpSensor(coordinator, interface.if_index),
                CatalystPortIpSourceSensor(coordinator, interface.if_index, "cdp"),
                CatalystPortIpSourceSensor(coordinator, interface.if_index, "observed"),
                CatalystNeighborDiscoverySensor(coordinator, interface.if_index),
            )
        )
    for port in coordinator.data.poe_ports.values():
        entities.append(CatalystPoePortPowerSensor(coordinator, port.index))
        entities.extend(
            CatalystPoePowerDetailSensor(coordinator, port.index, field)
            for field in ("allocated", "available", "maximum")
        )
    async_add_entities(entities)



class CatalystAccessVlanStatusSensor(CatalystInterfaceEntity, SensorEntity):
    """Read-only explanation of VLAN operational status on a physical port."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        port = coordinator.data.interfaces[if_index]
        self._attr_name = f"{port.name} access VLAN status"
        self._attr_unique_id = f"{coordinator.client.host}_if_{if_index}_access_vlan_status"

    @property
    def native_value(self) -> str:
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is None or port.access_vlan is None:
            return "unknown"
        if port.is_trunk is True:
            return "trunk"
        if port.access_vlan not in self.coordinator.data.operational_vlans:
            return "inactive"
        return "operational"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self.coordinator.data.interfaces.get(self.if_index)
        vlan = port.access_vlan if port is not None else None
        inactive = (
            port is not None and port.is_trunk is False and vlan is not None
            and vlan not in self.coordinator.data.operational_vlans
        )
        return {
            **self.catalyst_attributes,
            "access_vlan": vlan,
            "recovery_required": bool(inactive),
            "message": (
                f"Access VLAN {vlan} is inactive. Use VLAN Management to review recovery."
                if inactive else "No inactive access VLAN assignment detected."
            ),
            "vlan_management_url": "/cisco-catalyst-vlan",
        }


class CatalystDashboardContractSensor(CatalystEntity, SensorEntity):
    """Frontend discovery marker for the Cisco Catalyst dashboard contract."""

    _attr_name = "Dashboard contract"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_dashboard_contract"

    @property
    def native_value(self) -> int:
        return 1

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "cisco_catalyst_role": "switch",
            "dashboard_contract_version": 1,
            "is_cisco_catalyst_switch": True,
        }


class CatalystSnmpStatusSensor(CatalystEntity, SensorEntity):
    """Expose active SNMP mode and notification-listener status without secrets."""

    _attr_name = "SNMP status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_snmp_status"

    @property
    def native_value(self) -> str:
        return getattr(
            self.coordinator,
            "snmp_mode",
            "3 (authPriv)" if self.coordinator.client.version == "3" else "2c",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        enabled = bool(
            getattr(self.coordinator, "notification_listener_enabled", False)
        )
        port = getattr(self.coordinator, "notification_listener_port", 1162)
        return {
            "notification_listener": "enabled" if enabled else "disabled",
            "notification_listener_port": port,
            "notification_listener_transport": "UDP",
        }


class CatalystUptimeSensor(CatalystEntity, SensorEntity):
    _attr_name = "Uptime"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_uptime"

    @property
    def native_value(self) -> float:
        return self.coordinator.data.uptime_ticks / 100


class CatalystCpuSensor(CatalystEntity, SensorEntity):
    """Aggregate switch CPU utilization."""

    _attr_name = "CPU utilization"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_cpu_utilization"

    @property
    def native_value(self) -> int | None:
        cpu = self.coordinator.data.cpu
        return None if cpu is None else cpu.five_minutes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cpu = self.coordinator.data.cpu
        if cpu is None:
            return {}
        return {
            "five_seconds_percent": cpu.five_seconds,
            "one_minute_percent": cpu.one_minute,
            "five_minutes_percent": cpu.five_minutes,
            "cpu_index": cpu.index,
        }


class CatalystMemorySensor(CatalystEntity, SensorEntity):
    """Processor memory utilization."""

    _attr_name = "Memory used"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_memory_used"

    @property
    def native_value(self) -> float | None:
        memory = self.coordinator.data.memory
        if memory is None or memory.used_percent is None:
            return None
        return round(memory.used_percent, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        memory = self.coordinator.data.memory
        if memory is None:
            return {}
        return {
            "pool": memory.name,
            "used_bytes": memory.used_bytes,
            "free_bytes": memory.free_bytes,
            "total_bytes": memory.total_bytes,
            "largest_free_bytes": memory.largest_free_bytes,
        }


class CatalystMacMovementAnomalySensor(CatalystEntity, SensorEntity):
    """Expose bounded MAC movement and anomaly diagnostics for this integration run."""

    _attr_name = "MAC movement anomalies"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"recent_movements", "recent_anomalies"})

    def __init__(self, coordinator: CatalystCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_mac_movement_anomalies"

    @property
    def native_value(self) -> int:
        tracker = getattr(self.coordinator, "mac_movement_tracker", None)
        return 0 if tracker is None else tracker.anomaly_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tracker = getattr(self.coordinator, "mac_movement_tracker", None)
        if tracker is None:
            return {
                "history_scope": "coordinator_lifetime",
                "recent_movements": [],
                "recent_anomalies": [],
            }
        return {
            "history_scope": "coordinator_lifetime",
            "recent_movements": list(tracker.recent_movements),
            "recent_anomalies": list(tracker.recent_anomalies),
        }


class CatalystPoePowerSensor(CatalystEntity, SensorEntity):
    """Total current PoE consumption reported by all safely mapped PSE ports."""

    _attr_name = "PoE power consumption"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: CatalystCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_poe_power_used"

    @property
    def native_value(self) -> float | None:
        values = [
            port.power_consumption_mw
            for port in self.coordinator.data.poe_ports.values()
            if port.power_consumption_mw is not None
        ]
        if self.coordinator.data.poe_used_w is not None:
            return float(self.coordinator.data.poe_used_w)
        return round(sum(values) / 1000, 3) if values else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ports = self.coordinator.data.poe_ports.values()
        allocated = [
            port.power_allocated_mw
            for port in ports
            if port.power_allocated_mw is not None
        ]
        available = [
            port.power_available_mw
            for port in ports
            if port.power_available_mw is not None
        ]
        max_drawn = [
            port.max_power_drawn_mw
            for port in ports
            if port.max_power_drawn_mw is not None
        ]
        budget = self.coordinator.data.poe_budget_w
        used = self.coordinator.data.poe_used_w
        return {
            "poe_budget_w": budget,
            "poe_used_w": used,
            "poe_remaining_w": budget - used if budget is not None and used is not None else None,
            "detected_device_count": sum(port.device_detected is True for port in ports),
            "allocated_power_w": round(sum(allocated) / 1000, 3) if allocated else None,
            "available_power_w": round(sum(available) / 1000, 3) if available else None,
            "max_drawn_power_w": (
                round(sum(max_drawn) / 1000, 3) if max_drawn else None
            ),
        }


class CatalystTemperatureSensor(CatalystEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: CatalystCoordinator, ent_index: int) -> None:
        super().__init__(coordinator)
        self.ent_index = ent_index
        sensor = coordinator.data.temperatures[ent_index]
        self._attr_name = sensor.name
        self._attr_unique_id = f"{coordinator.client.host}_temperature_{ent_index}"

    @property
    def native_value(self) -> float | None:
        sensor = self.coordinator.data.temperatures.get(self.ent_index)
        return sensor.value_celsius if sensor else None

    @property
    def available(self) -> bool:
        sensor = self.coordinator.data.temperatures.get(self.ent_index)
        return (
            super().available
            and sensor is not None
            and sensor.status == CISCO_ENTITY_SENSOR_STATUS_OK
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sensor = self.coordinator.data.temperatures.get(self.ent_index)
        return (
            {}
            if sensor is None
            else {
                "entity_index": sensor.ent_index,
                "sensor_status": sensor.status,
                "update_rate": sensor.update_rate,
            }
        )


class CatalystFruStatusSensor(CatalystEntity, SensorEntity):
    """Power-supply or fan operational status from CISCO-ENTITY-FRU-CONTROL-MIB."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator, ent_index: int, kind: str) -> None:
        super().__init__(coordinator)
        self.ent_index = ent_index
        self.kind = kind
        item = (
            coordinator.data.power_supplies
            if kind == "power"
            else coordinator.data.fans
        )[ent_index]
        self._attr_name = f"{item.name} status"
        self._attr_unique_id = f"{coordinator.client.host}_{kind}_status_{ent_index}"

    @property
    def native_value(self) -> str | None:
        table = (
            self.coordinator.data.power_supplies
            if self.kind == "power"
            else self.coordinator.data.fans
        )
        item = table.get(self.ent_index)
        if item is None:
            return None
        names = FRU_POWER_STATUS_NAMES if self.kind == "power" else FAN_STATUS_NAMES
        return names.get(item.status, f"Unknown ({item.status})")

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        return {"entity_index": self.ent_index}


class CatalystCounterSensor(CatalystInterfaceEntity, SensorEntity):
    _attr_native_unit_of_measurement = "B"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: CatalystCoordinator, if_index: int, direction: str) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        self.direction = direction
        self.catalyst_role = f"{direction}_bytes"
        name = coordinator.data.interfaces[if_index].name
        self._attr_name = f"{name} {direction.upper()} bytes"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_{direction}_bytes"

    @property
    def native_value(self) -> int | None:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None:
            return None
        return interface.in_octets if self.direction == "rx" else interface.out_octets


class CatalystSpeedSensor(CatalystInterfaceEntity, SensorEntity):
    catalyst_role = "speed"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        name = coordinator.data.interfaces[if_index].name
        self._attr_name = f"{name} speed"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_speed"

    @property
    def native_value(self) -> str | None:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None:
            return None
        if interface.admin_status == 2:
            return "N/A (port disabled)"
        if interface.oper_status != 1:
            return "N/A (port down)"
        speed = interface.speed_mbps
        if speed is None:
            return "Unknown"
        if speed >= 1000:
            return f"{speed / 1000:g}G"
        return f"{speed:g}M"


class CatalystDiscardSensor(CatalystInterfaceEntity, SensorEntity):
    """Expose RX or TX interface discard counters as native diagnostics."""

    _attr_native_unit_of_measurement = "packets"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: CatalystCoordinator, if_index: int, direction: str
    ) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        self.direction = direction
        name = coordinator.data.interfaces[if_index].name
        self._attr_name = f"{name} {direction.upper()} discards"
        self._attr_unique_id = (
            f"{coordinator.client.host}_{if_index}_{direction}_discards"
        )

    @property
    def native_value(self) -> int | None:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None:
            return None
        return (
            interface.in_discards
            if self.direction == "rx"
            else interface.out_discards
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Intentionally omit dashboard-contract role metadata: these are
        # additive native diagnostics and do not change contract v1.
        return {}


class CatalystPoePortPowerSensor(CatalystPoeEntity, SensorEntity):
    """Expose per-port PoE consumption as a native child-device sensor."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator, poe_index: str) -> None:
        super().__init__(coordinator)
        self.poe_index = poe_index
        port = coordinator.data.poe_ports[poe_index]
        self._attr_name = f"{port.name} PoE power"
        self._attr_unique_id = f"{coordinator.client.host}_poe_{poe_index}_power"

    @staticmethod
    def _watts(value: int | None) -> float | None:
        return None if value is None else round(value / 1000, 3)

    @property
    def native_value(self) -> float | None:
        port = self.coordinator.data.poe_ports.get(self.poe_index)
        return None if port is None else self._watts(port.power_consumption_mw)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self.coordinator.data.poe_ports.get(self.poe_index)
        if port is None:
            return {}
        return {
            "poe_enabled": port.enabled,
            "powered_device_detected": port.device_detected,
            "allocated_power_w": self._watts(port.power_allocated_mw),
            "available_power_w": self._watts(port.power_available_mw),
            "max_power_drawn_w": self._watts(port.max_power_drawn_mw),
        }


class CatalystPortNetworkSensor(CatalystInterfaceEntity, SensorEntity):
    """Expose native Home Assistant VLAN and topology facts for a physical port."""

    catalyst_role = "network_mode"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"allowed_vlans"})

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        name = coordinator.data.interfaces[if_index].name
        self._attr_name = f"{name} network mode"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_network_mode"

    @property
    def native_value(self) -> str | None:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None:
            return None
        if interface.is_trunk is True:
            return "trunk"
        if interface.is_trunk is False:
            return "access"
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None:
            return {}
        cdp_count = len(interface.cdp_neighbors)
        lldp_count = len(interface.lldp_neighbors)
        attributes: dict[str, Any] = {
            **self.catalyst_attributes,
            "cdp_neighbor_count": cdp_count,
            "lldp_neighbor_count": lldp_count,
            "neighbor_discovered": bool(cdp_count or lldp_count),
        }
        if interface.access_vlan is not None:
            attributes["access_vlan"] = interface.access_vlan
        if interface.native_vlan is not None:
            attributes["native_vlan"] = interface.native_vlan
        if interface.allowed_vlans:
            attributes["allowed_vlans_count"] = len(interface.allowed_vlans)
            attributes["allowed_vlans"] = list(
                interface.allowed_vlans[:_PORT_DIAGNOSTIC_MAX_VLANS]
            )
            attributes["allowed_vlans_truncated"] = (
                len(interface.allowed_vlans) > _PORT_DIAGNOSTIC_MAX_VLANS
            )
        return attributes


class CatalystLearnedMacSensor(CatalystInterfaceEntity, SensorEntity):
    """Expose learned-MAC count with bounded current address attributes."""

    catalyst_role = "learned_macs"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"mac_addresses", "ip_addresses"})

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        name = coordinator.data.interfaces[if_index].name
        self._attr_name = f"{name} learned MACs"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_learned_macs"

    @property
    def native_value(self) -> int | None:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        return None if interface is None else len(interface.mac_addresses)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None:
            return {}
        attributes: dict[str, Any] = {**self.catalyst_attributes}
        if interface.mac_addresses:
            attributes["mac_addresses"] = list(
                interface.mac_addresses[:_PORT_DIAGNOSTIC_MAX_MACS]
            )
            attributes["mac_addresses_truncated"] = (
                len(interface.mac_addresses) > _PORT_DIAGNOSTIC_MAX_MACS
            )
        if interface.ip_addresses:
            attributes["learned_ip_count"] = len(interface.ip_addresses)
            attributes["ip_addresses"] = list(
                interface.ip_addresses[:_PORT_DIAGNOSTIC_MAX_IPS]
            )
            attributes["ip_addresses_truncated"] = (
                len(interface.ip_addresses) > _PORT_DIAGNOSTIC_MAX_IPS
            )
        return attributes


class CatalystPrimaryMacSensor(CatalystInterfaceEntity, SensorEntity):
    """Single learned endpoint MAC as a native state; never guess among multiple."""

    catalyst_role = "primary_mac"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        port = coordinator.data.interfaces[if_index]
        self._attr_name = f"{port.name} learned MAC address"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_primary_mac"

    @property
    def native_value(self) -> str | None:
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is None or len(port.mac_addresses) != 1:
            return None
        return port.mac_addresses[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self.coordinator.data.interfaces.get(self.if_index)
        return {
            **self.catalyst_attributes,
            "learned_mac_count": len(port.mac_addresses) if port else 0,
            "ambiguous": bool(port and len(port.mac_addresses) > 1),
        }


class CatalystPoePowerDetailSensor(CatalystPoeEntity, SensorEntity):
    """Expose existing PoE allocations and peak measurements as native states."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _FIELDS = {
        "allocated": ("PoE allocated power", "power_allocated_mw"),
        "available": ("PoE available power", "power_available_mw"),
        "maximum": ("PoE maximum observed power", "max_power_drawn_mw"),
    }

    def __init__(self, coordinator: CatalystCoordinator, poe_index: str, field: str) -> None:
        super().__init__(coordinator)
        self.poe_index = poe_index
        self._field = field
        port = coordinator.data.poe_ports[poe_index]
        self._attr_name = f"{port.name} {self._FIELDS[field][0]}"
        self._attr_unique_id = f"{coordinator.client.host}_poe_{poe_index}_{field}_power"

    @property
    def native_value(self) -> float | None:
        port = self.coordinator.data.poe_ports.get(self.poe_index)
        if port is None:
            return None
        milliwatts = getattr(port, self._FIELDS[self._field][1], None)
        return None if milliwatts is None else round(milliwatts / 1000, 3)


def _port_ip_sources(port: Any) -> tuple[list[str], list[str], list[str]]:
    """Keep MAC/IP correlation separate from CDP-advertised IP evidence."""
    correlated = sorted(set(port.ip_addresses))
    advertised = sorted({
        n.address for n in port.cdp_neighbors if n.address
    })
    return correlated, advertised, sorted(set(correlated) | set(advertised))


class CatalystLearnedIpSensor(CatalystInterfaceEntity, SensorEntity):
    """IP count from MAC/IP correlation (not CDP advertisements)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"ip_addresses"})

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        name = coordinator.data.interfaces[if_index].name
        self._attr_name = f"{name} learned endpoint IPs"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_learned_ips"

    @property
    def native_value(self) -> int | None:
        port = self.coordinator.data.interfaces.get(self.if_index)
        return None if port is None else len(_port_ip_sources(port)[0])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is None:
            return {}
        addresses = _port_ip_sources(port)[0]
        return {
            **self.catalyst_attributes,
            "discovery_source": "mac_ip_correlation",
            "ip_addresses": addresses[:_PORT_DIAGNOSTIC_MAX_IPS],
            "ip_addresses_truncated": len(addresses) > _PORT_DIAGNOSTIC_MAX_IPS,
        }


class CatalystPortIpSourceSensor(CatalystInterfaceEntity, SensorEntity):
    """CDP-advertised or combined observed port IP count."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"ip_addresses", "source_details"})

    def __init__(self, coordinator: CatalystCoordinator, if_index: int, source: str) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        self._source = source
        name = coordinator.data.interfaces[if_index].name
        label = "CDP neighbor IPs" if source == "cdp" else "observed port IPs"
        self._attr_name = f"{name} {label}"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_{source}_ips"

    @property
    def native_value(self) -> int | None:
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is None:
            return None
        endpoint, cdp, observed = _port_ip_sources(port)
        return len(cdp if self._source == "cdp" else observed)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is None:
            return {}
        endpoint, cdp, observed = _port_ip_sources(port)
        addresses = cdp if self._source == "cdp" else observed
        attrs = {
            **self.catalyst_attributes,
            "discovery_source": "cdp" if self._source == "cdp" else "combined",
            "ip_addresses": addresses[:_PORT_DIAGNOSTIC_MAX_IPS],
            "ip_addresses_truncated": len(addresses) > _PORT_DIAGNOSTIC_MAX_IPS,
        }
        if self._source != "cdp":
            attrs["endpoint_ip_count"] = len(endpoint)
            attrs["cdp_ip_count"] = len(cdp)
        return attrs


class CatalystNeighborDiscoverySensor(CatalystInterfaceEntity, SensorEntity):
    """Neighbor count with bounded CDP/LLDP discovery detail attributes."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"cdp_neighbors", "lldp_neighbors"})
    _MAX_NEIGHBORS = 16

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        name = coordinator.data.interfaces[if_index].name
        self._attr_name = f"{name} discovered neighbors"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_discovered_neighbors"

    @property
    def native_value(self) -> int | None:
        port = self.coordinator.data.interfaces.get(self.if_index)
        return None if port is None else len(port.cdp_neighbors) + len(port.lldp_neighbors)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is None:
            return {}
        return {
            **self.catalyst_attributes,
            "cdp_count": len(port.cdp_neighbors),
            "lldp_count": len(port.lldp_neighbors),
            "cdp_neighbors": [asdict(n) for n in port.cdp_neighbors[:self._MAX_NEIGHBORS]],
            "lldp_neighbors": [asdict(n) for n in port.lldp_neighbors[:self._MAX_NEIGHBORS]],
            "neighbors_truncated": (
                len(port.cdp_neighbors) > self._MAX_NEIGHBORS
                or len(port.lldp_neighbors) > self._MAX_NEIGHBORS
            ),
        }


class CatalystErrorSensor(CatalystInterfaceEntity, SensorEntity):
    catalyst_role = "errors"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"rx_discards", "tx_discards"})

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        name = coordinator.data.interfaces[if_index].name
        self._attr_name = f"{name} errors"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_errors"

    @property
    def native_value(self) -> int | None:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None or interface.in_errors is None or interface.out_errors is None:
            return None
        return interface.in_errors + interface.out_errors

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        return (
            {}
            if interface is None
            else {
                **self.catalyst_attributes,
                "rx_discards": interface.in_discards,
                "tx_discards": interface.out_discards,
            }
        )


class CatalystVlanReviewReadinessSensor(CatalystEntity, SensorEntity):
    """Read-only indicator of prerequisite data for a VLAN proposal review."""

    _attr_name = "VLAN review readiness"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CatalystCoordinator, options: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_vlan_review_readiness"
        self._options = options

    def _assessment(self) -> tuple[str, list[str]]:
        blockers: list[str] = []
        try:
            protected = get_protected_interfaces(self._options)
        except (TypeError, ValueError):
            protected = None
            blockers.append("invalid_protected_interface_options")
        if protected is None:
            blockers.append("protected_interfaces_not_configured")
        freshness = assess_snapshot_freshness(
            getattr(self.coordinator, "last_successful_poll_at", None),
            datetime.now(timezone.utc),
            update_succeeded=bool(getattr(self.coordinator, "last_update_success", False)),
        )
        blockers.extend(freshness.reasons)
        return ("blocked" if blockers else "ready_for_review", blockers)

    @property
    def native_value(self) -> str:
        return self._assessment()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        _, blockers = self._assessment()
        return {
            "read_only": True,
            "grants_write_permission": False,
            "blockers": blockers,
            "scope": "prerequisites_only_not_a_per_port_vlan_approval",
        }
