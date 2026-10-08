"""Binary sensors for Cisco Catalyst."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CatalystCoordinator
from .entity import CatalystInterfaceEntity


def _format_vlan_ranges(vlans: list[int]) -> str:
    """Compact VLAN IDs for HA state attributes."""
    if not vlans:
        return ""
    ordered = sorted(set(vlans))
    ranges: list[str] = []
    start = previous = ordered[0]
    for vlan in ordered[1:]:
        if vlan == previous + 1:
            previous = vlan
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = vlan
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(ranges)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[CatalystCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up interface link sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        CatalystLinkSensor(coordinator, interface.if_index)
        for interface in coordinator.data.interfaces.values()
    )


class CatalystLinkSensor(CatalystInterfaceEntity, BinarySensorEntity):
    """Physical interface operational state and learned endpoint metadata."""

    catalyst_role = "link"

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        interface = coordinator.data.interfaces[if_index]
        self._attr_name = f"{interface.name} link"
        self._attr_unique_id = f"{coordinator.client.host}_{if_index}_link"

    @property
    def is_on(self) -> bool | None:
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None or interface.oper_status is None:
            return None
        return interface.oper_status == 1

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose discovered L2/L3 endpoints and CDP peers without entity explosion."""
        interface = self.coordinator.data.interfaces.get(self.if_index)
        if interface is None:
            return {}
        attributes: dict[str, Any] = {
            **self.catalyst_attributes,
            "access_vlan": interface.access_vlan,
            "port_mode": (
                "trunk"
                if interface.is_trunk is True
                else "access"
                if interface.is_trunk is False
                else None
            ),
            "native_vlan": interface.native_vlan,
            "mac_addresses": interface.mac_addresses,
            "ip_addresses": interface.ip_addresses,
        }
        if interface.is_trunk is True:
            attributes["allowed_vlans"] = _format_vlan_ranges(interface.allowed_vlans)
        poe = next(
            (
                port
                for port in self.coordinator.data.poe_ports.values()
                if port.name == interface.name
            ),
            None,
        )
        if poe is not None:
            attributes["poe"] = {
                "enabled": poe.enabled,
                "device_detected": poe.device_detected,
                "allocated_power_w": (
                    round(poe.power_allocated_mw / 1000, 3)
                    if poe.power_allocated_mw is not None
                    else None
                ),
                "available_power_w": (
                    round(poe.power_available_mw / 1000, 3)
                    if poe.power_available_mw is not None
                    else None
                ),
                "consumption_w": (
                    round(poe.power_consumption_mw / 1000, 3)
                    if poe.power_consumption_mw is not None
                    else None
                ),
                "max_drawn_w": (
                    round(poe.max_power_drawn_mw / 1000, 3)
                    if poe.max_power_drawn_mw is not None
                    else None
                ),
            }
        if interface.cdp_neighbors:
            attributes["cdp_neighbors"] = [
                {
                    "device_id": neighbor.device_id,
                    "address": neighbor.address,
                    "port_id": neighbor.port_id,
                    "platform": neighbor.platform,
                }
                for neighbor in interface.cdp_neighbors
            ]
        if interface.lldp_neighbors:
            attributes["lldp_neighbors"] = [
                {
                    "system_name": neighbor.system_name,
                    "chassis_id": neighbor.chassis_id,
                    "port_id": neighbor.port_id,
                    "port_description": neighbor.port_description,
                }
                for neighbor in interface.lldp_neighbors
            ]
        return attributes
