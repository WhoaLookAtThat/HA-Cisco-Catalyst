"""Safe access-VLAN controls for Cisco Catalyst physical interfaces."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CISCO_VM_VLAN, CISCO_VM_VLAN_TYPE_STATIC
from .coordinator import CatalystCoordinator
from .entity import CatalystInterfaceEntity
from .write import async_write_with_readback

MIN_VLAN_ID = 1
MAX_VLAN_ID = 4094
RESERVED_ETHERNET_VLANS = frozenset(range(1002, 1006))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[CatalystCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up access-VLAN controls only where access mode is authoritative."""
    coordinator = entry.runtime_data
    if not coordinator.write_enabled:
        return
    async_add_entities(
        CatalystAccessVlanNumber(coordinator, port.if_index)
        for port in coordinator.data.interfaces.values()
        if (
            port.access_vlan is not None
            and port.access_vlan in coordinator.data.operational_vlans
            and port.access_vlan_type == CISCO_VM_VLAN_TYPE_STATIC
            and port.is_trunk is False
        )
    )


class CatalystAccessVlanNumber(CatalystInterfaceEntity, NumberEntity):
    """Access VLAN backed by CISCO-VLAN-MEMBERSHIP-MIB vmVlan."""

    catalyst_role = "access_vlan"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = MIN_VLAN_ID
    _attr_native_max_value = MAX_VLAN_ID
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        port = coordinator.data.interfaces[if_index]
        self._attr_name = f"{port.name} access VLAN"
        self._attr_unique_id = f"{coordinator.client.host}_if_{if_index}_access_vlan"

    @property
    def available(self) -> bool:
        """Expose the control only for a confirmed non-trunk interface."""
        if not super().available:
            return False
        port = self.coordinator.data.interfaces.get(self.if_index)
        return (
            port is not None
            and port.access_vlan is not None
            and port.access_vlan in self.coordinator.data.operational_vlans
            and port.access_vlan_type == CISCO_VM_VLAN_TYPE_STATIC
            and port.is_trunk is False
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            **self.catalyst_attributes,
            "credential_access": (
                "read_write" if self.coordinator.write_enabled else "read_only"
            ),
        }

    @property
    def native_value(self) -> int | None:
        oid = f"{CISCO_VM_VLAN}.{self.if_index}"
        pending = self.coordinator.pending_writes.get(oid)
        if pending is not None:
            return int(pending)
        port = self.coordinator.data.interfaces.get(self.if_index)
        return port.access_vlan if port is not None else None

    def _apply_access_vlan(self, value: int) -> None:
        """Apply an exact-OID verified access VLAN to the coordinator snapshot."""
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is not None:
            port.access_vlan = value

    async def async_set_native_value(self, value: float) -> None:
        """Set and verify an access VLAN through CISCO-VLAN-MEMBERSHIP-MIB."""
        if int(value) != value:
            raise HomeAssistantError("Access VLAN must be a whole-number VLAN ID")
        vlan = int(value)
        if not MIN_VLAN_ID <= vlan <= MAX_VLAN_ID:
            raise HomeAssistantError(
                f"Access VLAN must be between {MIN_VLAN_ID} and {MAX_VLAN_ID}"
            )
        if vlan in RESERVED_ETHERNET_VLANS:
            raise HomeAssistantError(
                "Access VLAN 1002-1005 is reserved for legacy FDDI/Token Ring use"
            )
        if vlan not in self.coordinator.data.operational_vlans:
            raise HomeAssistantError(
                "Access VLAN must already exist and be operational on the switch"
            )

        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is None or port.is_trunk is not False:
            raise HomeAssistantError(
                "Access VLAN writes are allowed only on a confirmed non-trunk interface"
            )
        if port.access_vlan is None:
            raise HomeAssistantError(
                "Access VLAN is unavailable for this interface; refusing SNMP SET"
            )
        if port.access_vlan_type != CISCO_VM_VLAN_TYPE_STATIC:
            raise HomeAssistantError(
                "Access VLAN writes require Cisco vmVlanType static(1)"
            )

        oid = f"{CISCO_VM_VLAN}.{self.if_index}"
        await async_write_with_readback(
            self.coordinator,
            oid,
            vlan,
            writer=self.coordinator.client.set_integer,
            normalize_readback=int,
            expected_state=lambda: (
                (current := self.coordinator.data.interfaces.get(self.if_index))
                is not None
                and current.access_vlan == vlan
            ),
            apply_verified_state=lambda: self._apply_access_vlan(vlan),
        )
