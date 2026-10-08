"""Port and PoE switches for Cisco Catalyst."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CPE_PORT_ENABLE,
    IF_ADMIN_DOWN,
    IF_ADMIN_STATUS,
    IF_ADMIN_UP,
    POE_AUTO,
    POE_DISABLE,
)
from .coordinator import CatalystCoordinator
from .entity import CatalystInterfaceEntity, CatalystPoeEntity
from .write import async_write_with_readback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[CatalystCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up interface administration and PoE switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        CatalystPortAdminSwitch(coordinator, port.if_index)
        for port in coordinator.data.interfaces.values()
    ]
    entities.extend(
        CatalystPoeSwitch(coordinator, port.index)
        for port in coordinator.data.poe_ports.values()
    )
    async_add_entities(entities)


class CatalystPortAdminSwitch(CatalystInterfaceEntity, SwitchEntity):
    """Administrative up/down control for one physical interface."""

    catalyst_role = "admin"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        port = coordinator.data.interfaces[if_index]
        self._attr_name = f"{port.name} port enabled"
        self._attr_unique_id = f"{coordinator.client.host}_if_{if_index}_admin"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            **self.catalyst_attributes,
            "credential_access": (
                "read_write" if self.coordinator.write_enabled else "read_only"
            ),
        }

    @property
    def is_on(self) -> bool | None:
        pending = self.coordinator.pending_writes.get(
            f"{IF_ADMIN_STATUS}.{self.if_index}"
        )
        if pending is not None:
            return pending == IF_ADMIN_UP
        port = self.coordinator.data.interfaces.get(self.if_index)
        return (
            None
            if port is None or port.admin_status is None
            else port.admin_status == IF_ADMIN_UP
        )

    async def _async_set_admin_status(self, value: int) -> None:
        await async_write_with_readback(
            self.coordinator,
            f"{IF_ADMIN_STATUS}.{self.if_index}",
            value,
            writer=self.coordinator.client.set_integer,
            normalize_readback=int,
            expected_state=lambda: (
                (port := self.coordinator.data.interfaces.get(self.if_index))
                is not None
                and port.admin_status == value
            ),
            apply_verified_state=lambda: self._apply_admin_status(value),
        )

    def _apply_admin_status(self, value: int) -> None:
        """Apply an exact-OID verified admin state to the coordinator snapshot."""
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is not None:
            port.admin_status = value

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._async_set_admin_status(IF_ADMIN_UP)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._async_set_admin_status(IF_ADMIN_DOWN)


class CatalystPoeSwitch(CatalystPoeEntity, SwitchEntity):
    """PoE administrative control for one safely mapped physical interface."""

    catalyst_role = "poe"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: CatalystCoordinator, poe_index: str) -> None:
        super().__init__(coordinator)
        self.poe_index = poe_index
        port = coordinator.data.poe_ports[poe_index]
        self._attr_name = f"{port.name} PoE"
        self._attr_unique_id = f"{coordinator.client.host}_poe_{poe_index}"

    @property
    def is_on(self) -> bool | None:
        pending = self.coordinator.pending_writes.get(
            f"{CPE_PORT_ENABLE}.{self.poe_index}"
        )
        if pending is not None:
            return pending != POE_DISABLE
        port = self.coordinator.data.poe_ports.get(self.poe_index)
        return port.enabled if port is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self.coordinator.data.poe_ports.get(self.poe_index)
        if port is None:
            return {}

        def watts(value: int | None) -> float | None:
            return None if value is None else round(value / 1000, 3)

        return {
            **self.catalyst_attributes,
            "credential_access": (
                "read_write" if self.coordinator.write_enabled else "read_only"
            ),
            "device_detected": port.device_detected,
            "power_consumption_w": watts(port.power_consumption_mw),
            "power_allocated_w": watts(port.power_allocated_mw),
            "power_available_w": watts(port.power_available_mw),
            "max_power_drawn_w": watts(port.max_power_drawn_mw),
        }

    async def _async_set_poe(self, value: int) -> None:
        await async_write_with_readback(
            self.coordinator,
            f"{CPE_PORT_ENABLE}.{self.poe_index}",
            value,
            writer=self.coordinator.client.set_integer,
            normalize_readback=int,
            expected_state=lambda: (
                (port := self.coordinator.data.poe_ports.get(self.poe_index))
                is not None
                and port.enabled == (value != POE_DISABLE)
            ),
            apply_verified_state=lambda: self._apply_poe_state(value),
        )

    def _apply_poe_state(self, value: int) -> None:
        """Apply an exact-OID verified PoE state to the coordinator snapshot."""
        port = self.coordinator.data.poe_ports.get(self.poe_index)
        if port is not None:
            port.enabled = value != POE_DISABLE

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._async_set_poe(POE_AUTO)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._async_set_poe(POE_DISABLE)
