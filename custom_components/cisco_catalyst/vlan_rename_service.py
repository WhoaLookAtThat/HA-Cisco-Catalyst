"""Home Assistant response action for renaming a VLAN."""

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .vlan_admin import require_vlan_admin
from .const import DOMAIN
from .vlan_rename import rename_vlan
from .protected_vlan_options import configured_protected_vlans


def register_vlan_rename_service(hass):
    if hass.services.has_service(DOMAIN, "rename_vlan"):
        return

    async def rename(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        coordinator = entry.runtime_data
        if not coordinator.write_enabled:
            raise HomeAssistantError("Read/write credentials are required")
        await require_vlan_admin(hass, call)
        async with coordinator.write_lock:
            protected = configured_protected_vlans(entry.options)
            if protected and call.data["vlan_id"] in protected:
                raise HomeAssistantError("VLAN is protected; remove protection before renaming")
            async with coordinator.io_lock:
                result = await rename_vlan(coordinator.client, call.data["vlan_id"], call.data["name"])
        await coordinator.async_request_refresh()
        return result

    hass.services.async_register(
        DOMAIN, "rename_vlan", rename,
        schema=vol.Schema({
            vol.Required("entry_id"): str,
            vol.Required("vlan_id"): vol.All(vol.Coerce(int), vol.Range(min=2, max=1001)),
            vol.Required("name"): vol.All(str, vol.Match(r"^[A-Za-z0-9_-]{1,32}$")),
        }),
        supports_response=SupportsResponse.ONLY,
    )
