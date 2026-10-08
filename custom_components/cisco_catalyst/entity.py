"""Shared entities for Cisco Catalyst."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CatalystCoordinator


class CatalystEntity(CoordinatorEntity[CatalystCoordinator]):
    """Base entity attached to the Catalyst chassis device."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        chassis = data.chassis
        model = chassis.model.strip() if chassis and chassis.model.strip() else "Catalyst"
        serial = chassis.serial.strip() if chassis and chassis.serial.strip() else None
        sw_version = (
            chassis.software_rev.strip()
            if chassis and chassis.software_rev.strip()
            else None
        )
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.client.host)},
            name=data.sys_name or "Cisco Catalyst",
            manufacturer="Cisco",
            model=model,
            serial_number=serial,
            sw_version=sw_version,
        )


def _physical_layout(name: str) -> dict[str, Any]:
    """Return stable Catalyst physical-layout metadata from IOS interface identity."""
    match = re.search(r"(\d+)/(\d+)/(\d+)$", name)
    if match is None:
        return {
            "physical_group": "unknown",
            "physical_position": None,
            "physical_member": None,
            "physical_slot": None,
            "physical_port": None,
            "member": None,
            "slot": None,
            "port": None,
        }
    member, slot, position = (int(value) for value in match.groups())
    return {
        "physical_group": "primary" if slot == 0 else "additional",
        "physical_member": member,
        "physical_slot": slot,
        "physical_port": position,
        "physical_position": position,
        "member": member,
        "slot": slot,
        "port": position,
    }


def _interface_contract_attributes(
    host: str, if_index: int, name: str, role: str
) -> dict[str, Any]:
    """Return the stable frontend contract for one physical interface entity."""
    return {
        "cisco_catalyst_role": role,
        "interface_id": f"{host}:interface:{if_index}",
        "interface_name": name,
        "is_physical": True,
        "if_index": if_index,
        **_physical_layout(name),
    }


class CatalystInterfaceEntity(CatalystEntity):
    """Base entity attached to a physical interface child device."""

    if_index: int
    catalyst_role: str = "interface"

    @property
    def catalyst_attributes(self) -> dict[str, Any]:
        """Frontend-visible integration contract for interface entities."""
        interface = self.coordinator.data.interfaces.get(self.if_index)
        name = interface.name if interface is not None else ""
        return _interface_contract_attributes(
            self.coordinator.client.host,
            self.if_index,
            name,
            self.catalyst_role,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.catalyst_attributes

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        interface = data.interfaces.get(self.if_index)
        name = interface.name if interface is not None else f"Interface {self.if_index}"
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{self.coordinator.client.host}:interface:{self.if_index}",
                )
            },
            name=name,
            manufacturer="Cisco",
            model="Catalyst Ethernet port",
            via_device=(DOMAIN, self.coordinator.client.host),
        )
    @property
    def available(self) -> bool:
        return super().available and self.if_index in self.coordinator.data.interfaces


class CatalystPoeEntity(CatalystInterfaceEntity):
    """Base PoE entity attached to its physical interface child device."""

    poe_index: str
    catalyst_role: str = "poe"

    @property
    def if_index(self) -> int:
        poe = self.coordinator.data.poe_ports.get(self.poe_index)
        if poe is not None:
            for if_index, interface in self.coordinator.data.interfaces.items():
                if interface.name == poe.name:
                    return if_index
        return -1

    @property
    def device_info(self) -> DeviceInfo:
        poe = self.coordinator.data.poe_ports.get(self.poe_index)
        if poe is not None:
            for if_index, interface in self.coordinator.data.interfaces.items():
                if interface.name == poe.name:
                    return DeviceInfo(
                        identifiers={
                            (
                                DOMAIN,
                                f"{self.coordinator.client.host}:interface:{if_index}",
                            )
                        },
                        name=interface.name,
                        manufacturer="Cisco",
                        model="Catalyst Ethernet port",
                        via_device=(DOMAIN, self.coordinator.client.host),
                    )
        return super().device_info


    @property
    def available(self) -> bool:
        return super().available and self.poe_index in self.coordinator.data.poe_ports
