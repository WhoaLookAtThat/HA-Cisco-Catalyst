"""Administrator-only VLAN protection settings."""
import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .vlan_admin import require_vlan_admin
from .protected_interface_options import parse_protected_interfaces
from .protected_vlan_options import parse_protected_vlans, configured_protected_vlans

def register_vlan_protection_services(hass):
    if hass.services.has_service(DOMAIN, "get_vlan_protection"):
        return
    async def get_settings(call):
        await require_vlan_admin(hass, call)
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise HomeAssistantError("Switch entry unavailable")
        return {"protected_interfaces": entry.options.get("protected_interfaces", ""),
                "protected_vlans": entry.options.get("protected_vlans", "")}

    async def save_settings(call):
        await require_vlan_admin(hass, call)
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise HomeAssistantError("Switch entry unavailable")
        interfaces = call.data["protected_interfaces"]
        vlans = call.data["protected_vlans"]
        try:
            parse_protected_interfaces(interfaces)
            parse_protected_vlans(vlans)
        except (ValueError, TypeError) as err:
            raise HomeAssistantError(str(err)) from err
        updated = dict(entry.options)
        updated.update(protected_interfaces=interfaces, protected_vlans=vlans)
        hass.config_entries.async_update_entry(entry, options=updated)
        return {"status": "saved"}

    hass.services.async_register(DOMAIN, "get_vlan_protection", get_settings,
        schema=vol.Schema({vol.Required("entry_id"): str}),
        supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "save_vlan_protection", save_settings,
        schema=vol.Schema({vol.Required("entry_id"): str,
                           vol.Required("protected_interfaces"): str,
                           vol.Required("protected_vlans"): str}),
        supports_response=SupportsResponse.ONLY)

    async def set_protected(call):
        await require_vlan_admin(hass, call)
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Switch entry unavailable")
        vlan_id = call.data["vlan_id"]
        if not 2 <= vlan_id <= 1001:
            raise HomeAssistantError("This VLAN cannot be toggled")
        coordinator = entry.runtime_data
        async with coordinator.write_lock:
            if vlan_id not in coordinator.data.operational_vlans:
                raise HomeAssistantError("VLAN is not currently operational")
            protected = set(configured_protected_vlans(entry.options) or ())
            if call.data["protected"]:
                protected.add(vlan_id)
            else:
                protected.discard(vlan_id)
            updated = dict(entry.options)
            updated["protected_vlans"] = ", ".join(str(v) for v in sorted(protected))
            hass.config_entries.async_update_entry(entry, options=updated)
        return {"status": "saved", "vlan_id": vlan_id, "protected": call.data["protected"]}

    hass.services.async_register(DOMAIN, "set_vlan_protected", set_protected,
        schema=vol.Schema({vol.Required("entry_id"): str,
                           vol.Required("vlan_id"): vol.All(vol.Coerce(int),vol.Range(min=2,max=1001)),
                           vol.Required("protected"): bool}),
        supports_response=SupportsResponse.ONLY)
