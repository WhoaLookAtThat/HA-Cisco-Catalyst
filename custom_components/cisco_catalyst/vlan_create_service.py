"""Home Assistant service for creating a normal-range VLAN using SNMP."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .vlan_admin import require_vlan_admin
from .const import DOMAIN
from .vlan_creation import execute_vlan_creation

SERVICE_CREATE_VLAN = "create_vlan"
CREATE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): str,
    vol.Required("vlan_id"): vol.All(vol.Coerce(int), vol.Range(min=2, max=1001)),
    vol.Required("name"): vol.All(str, vol.Length(min=1, max=32)),
})


def register_create_vlan_service(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CREATE_VLAN):
        return

    async def create(call: ServiceCall) -> dict[str, object]:
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        coordinator = entry.runtime_data
        if not coordinator.write_enabled:
            raise HomeAssistantError("Read/write SNMP credentials are required")
        await require_vlan_admin(hass, call)
        async with coordinator.write_lock:
            async with coordinator.io_lock:
                result = await execute_vlan_creation(
                    coordinator.client, call.data["vlan_id"], call.data["name"]
                )
        await coordinator.async_request_refresh()
        return result

    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_VLAN, create,
        schema=CREATE_SCHEMA, supports_response=SupportsResponse.ONLY,
    )
