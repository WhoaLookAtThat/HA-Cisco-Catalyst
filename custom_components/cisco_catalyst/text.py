"""Editable interface descriptions for Cisco Catalyst."""

from __future__ import annotations

from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import IF_ALIAS
from .coordinator import CatalystCoordinator
from .entity import CatalystInterfaceEntity
from .write import async_write_with_readback


def _text_readback(value: Any) -> str:
    """Normalize a PySNMP OCTET STRING or test double to text."""
    try:
        return value.prettyPrint()
    except AttributeError:
        return str(value)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[CatalystCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up editable Cisco interface descriptions."""
    coordinator = entry.runtime_data
    async_add_entities(
        CatalystPortDescription(coordinator, port.if_index)
        for port in coordinator.data.interfaces.values()
    )


class CatalystPortDescription(CatalystInterfaceEntity, TextEntity):
    """Cisco interface description backed by IF-MIB ifAlias."""

    catalyst_role = "description"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min = 0
    _attr_native_max = 64

    def __init__(self, coordinator: CatalystCoordinator, if_index: int) -> None:
        super().__init__(coordinator)
        self.if_index = if_index
        port = coordinator.data.interfaces[if_index]
        self._attr_name = f"{port.name} description"
        self._attr_unique_id = f"{coordinator.client.host}_if_{if_index}_description"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            **self.catalyst_attributes,
            "credential_access": (
                "read_write" if self.coordinator.write_enabled else "read_only"
            ),
        }

    @property
    def native_value(self) -> str | None:
        pending = self.coordinator.pending_writes.get(f"{IF_ALIAS}.{self.if_index}")
        if pending is not None:
            return str(pending)
        port = self.coordinator.data.interfaces.get(self.if_index)
        return port.description if port is not None else None

    def _apply_description(self, value: str) -> None:
        """Apply an exact-OID verified description to the coordinator snapshot."""
        port = self.coordinator.data.interfaces.get(self.if_index)
        if port is not None:
            port.description = value

    async def async_set_value(self, value: str) -> None:
        """Set and verify the Cisco interface description through IF-MIB ifAlias."""
        await async_write_with_readback(
            self.coordinator,
            f"{IF_ALIAS}.{self.if_index}",
            value,
            writer=self.coordinator.client.set_string,
            normalize_readback=_text_readback,
            expected_state=lambda: (
                (port := self.coordinator.data.interfaces.get(self.if_index))
                is not None
                and port.description == value
            ),
            apply_verified_state=lambda: self._apply_description(value),
        )
