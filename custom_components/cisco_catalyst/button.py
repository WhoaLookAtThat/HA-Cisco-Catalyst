"""Button entities for Cisco Catalyst."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CatalystCoordinator
from .entity import CatalystEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[CatalystCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Catalyst buttons."""
    async_add_entities([CatalystRefreshButton(entry.runtime_data)])


class CatalystRefreshButton(CatalystEntity, ButtonEntity):
    """Request an immediate read-only refresh from the switch."""

    _attr_name = "Refresh data"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: CatalystCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_refresh_data"

    async def async_press(self) -> None:
        """Refresh all coordinator data immediately."""
        await self.coordinator.async_request_refresh()
