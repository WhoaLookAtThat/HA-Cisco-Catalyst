"""Sensors for Cisco Catalyst."""

from __future__ import annotations

from typing import Any

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
                CatalystLearnedMacSensor(coordinator, interface.if_index),
            )
        )
    entities.extend(
        CatalystPoePortPowerSensor(coordinator, port.index)
        for port in coordinator.data.poe_ports.values()
    )
    async_add_entities(entities)


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
