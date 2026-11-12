"""Read-only VLAN inventory action for the Catalyst VLAN panel."""

import voluptuous as vol
from homeassistant.core import ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

VLAN_STATE_OID = "1.3.6.1.4.1.9.9.46.1.3.1.1.2"
VLAN_NAME_OID = "1.3.6.1.4.1.9.9.46.1.3.1.1.4"


def register_vlan_inventory_service(hass):
    """Register a read-only response action."""
    if hass.services.has_service(DOMAIN, "list_vlans"):
        return

    async def list_vlans(call: ServiceCall):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        coordinator = entry.runtime_data
        async with coordinator.io_lock:
            states = await coordinator.client.walk(VLAN_STATE_OID)
            names = await coordinator.client.walk(VLAN_NAME_OID)
        result = []
        prefix = VLAN_STATE_OID + "."
        for oid, state in states.items():
            key = str(oid).lstrip(".")
            if not key.startswith(prefix) or int(state) != 1:
                continue
            suffix = key[len(prefix):]
            parts = suffix.split(".")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                continue
            vlan_id = int(parts[1])
            raw_name = names.get(VLAN_NAME_OID + "." + suffix, names.get("." + VLAN_NAME_OID + "." + suffix))
            if isinstance(raw_name, bytes):
                name = raw_name.decode("utf-8", errors="replace")
            else:
                name = str(raw_name) if raw_name is not None else ""
            result.append({"id": vlan_id, "name": name})
        return {"vlans": sorted(result, key=lambda v: v["id"])}

    hass.services.async_register(
        DOMAIN, "list_vlans", list_vlans,
        schema=vol.Schema({vol.Required("entry_id"): str}),
        supports_response=SupportsResponse.ONLY,
    )
