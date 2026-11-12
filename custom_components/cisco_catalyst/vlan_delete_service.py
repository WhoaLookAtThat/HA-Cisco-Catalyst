"""Home Assistant action for intentional VLAN deletion."""

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .vlan_admin import require_vlan_admin
from .const import DOMAIN
from .vlan_delete import delete_vlan
from .vlan_bulk_move_preview import preview_bulk_move
from .vlan_bulk_move import move_selected_access_ports
from .vlan_orphan_recovery import recover_orphaned_port
from .protected_interface_options import get_protected_interfaces


def register_vlan_delete_service(hass):
    if hass.services.has_service(DOMAIN, "delete_vlan"):
        return

    async def delete(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        coordinator = entry.runtime_data
        if not coordinator.write_enabled:
            raise HomeAssistantError("Read/write credentials required")
        vlan = call.data["vlan_id"]
        if call.data["confirmation"] != f"DELETE {vlan}":
            raise HomeAssistantError("Deletion confirmation does not match VLAN ID")
        await require_vlan_admin(hass, call)
        async with coordinator.write_lock:
            async with coordinator.io_lock:
                result = await delete_vlan(
                    coordinator, entry.options, vlan, call.data.get("destination_vlan")
                )
        # The switch deletion was verified; a later HA refresh failure should
        # be reported separately rather than disguising the successful write.
        try:
            await coordinator.async_request_refresh()
        except Exception:
            result["refresh_warning"] = (
                "Switch change verified; Home Assistant refresh failed. "
                "Refresh inventory before the next operation."
            )
        return result

    async def preview(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        vlan = call.data["vlan_id"]
        ports = sorted(p.name for p in entry.runtime_data.data.interfaces.values()
                       if p.access_vlan == vlan)
        protected = get_protected_interfaces(entry.options)
        blocked = ports if protected is None else [name for name in ports if name in protected]
        return {
            "vlan_id": vlan,
            "access_ports": ports,
            "protected_or_unverified_ports": blocked,
            "snapshot_only": True,
            "note": "Last polling snapshot; not a fresh switch read. Other VLAN dependencies may exist.",
        }

    async def preview_reassignment(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        return preview_bulk_move(
            entry.runtime_data.data, entry.options,
            call.data["source_vlan"], call.data["destination_vlan"],
        )

    async def reassign_selected(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        coordinator = entry.runtime_data
        if not coordinator.write_enabled:
            raise HomeAssistantError("Read/write credentials required")
        source = call.data["source_vlan"]
        destination = call.data["destination_vlan"]
        names = call.data["ports"]
        if call.data["confirmation"] != f"MOVE {len(names)} PORTS TO {destination}":
            raise HomeAssistantError("Bulk move confirmation mismatch")
        await require_vlan_admin(hass, call)
        async with coordinator.write_lock:
            async with coordinator.io_lock:
                result = await move_selected_access_ports(
                    coordinator, entry.options, source, destination, names
                )
        try:
            await coordinator.async_request_refresh()
        except Exception:
            # SNMP write/readback already succeeded; a failed HA refresh
            # must not falsely classify committed switch changes as failed.
            result["refresh_warning"] = "Home Assistant refresh failed after verified switch changes"
        return result

    async def recover_orphan(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        coordinator = entry.runtime_data
        if not coordinator.write_enabled:
            raise HomeAssistantError("Read/write credentials required")
        index = call.data["if_index"]
        name = call.data["expected_interface_name"]
        source = call.data["source_vlan"]
        target = call.data["destination_vlan"]
        if name in ("GigabitEthernet1/0/24", "GigabitEthernet1/0/44", "Gi1/0/24", "Gi1/0/44"):
            raise HomeAssistantError("Protected infrastructure interface cannot be recovered")
        if call.data["confirmation"] != f"RECOVER TO {target}":
            raise HomeAssistantError("Recovery confirmation mismatch")
        await require_vlan_admin(hass, call)
        async with coordinator.write_lock:
            async with coordinator.io_lock:
                result = await recover_orphaned_port(
                    coordinator, entry.options, index, name, source, target
                )
        try:
            await coordinator.async_request_refresh()
        except Exception:
            result["refresh_warning"] = "Switch readback verified; HA refresh failed"
        return result

    async def port_overview(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry unavailable")
        data = entry.runtime_data.data
        result = {}
        for port in data.interfaces.values():
            if port.access_vlan is None or port.is_trunk is not False:
                continue
            poe = next((item for item in getattr(data, "poe_ports", {}).values() if item.name == port.name), None)
            poe_state = "unavailable"
            if poe is not None:
                if not poe.enabled:
                    poe_state = "disabled"
                elif poe.device_detected is True or (poe.power_consumption_mw or 0) > 0:
                    poe_state = "powering"
                elif poe.device_detected is False:
                    poe_state = "idle"
                else:
                    poe_state = "enabled"
            key = str(port.access_vlan)
            result.setdefault(key, []).append({
                "name": port.name,
                "description": port.description or "",
                "link": "up" if port.oper_status == 1 else ("down" if port.oper_status == 2 else "unknown"),
                "poe": poe_state,
                "if_index": port.if_index,
            })
        for ports in result.values():
            ports.sort(key=lambda row: row["name"])
        return {
            "ports_by_vlan": result,
            "snapshot_only": True,
            "note": "Access-port assignments from last polling snapshot, not live switch reads. Trunk memberships excluded.",
        }

    hass.services.async_register(
        DOMAIN, "recover_orphaned_access_port", recover_orphan,
        schema=vol.Schema({
            vol.Required("entry_id"): str,
            vol.Required("if_index"): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Required("expected_interface_name"): str,
            vol.Required("source_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4094)),
            vol.Required("destination_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1001)),
            vol.Required("confirmation"): str,
        }),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN, "reassign_vlan_access_ports", reassign_selected,
        schema=vol.Schema({
            vol.Required("entry_id"): str,
            vol.Required("source_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1001)),
            vol.Required("destination_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1001)),
            vol.Required("ports"): vol.All([str], vol.Length(min=1, max=52)),
            vol.Required("confirmation"): str,
        }),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN, "vlan_port_overview", port_overview,
        schema=vol.Schema({vol.Required("entry_id"): str}),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN, "preview_vlan_bulk_reassignment", preview_reassignment,
        schema=vol.Schema({
            vol.Required("entry_id"): str,
            vol.Required("source_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4094)),
            vol.Required("destination_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4094)),
        }),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN, "preview_vlan_delete", preview,
        schema=vol.Schema({
            vol.Required("entry_id"): str,
            vol.Required("vlan_id"): vol.All(vol.Coerce(int), vol.Range(min=2, max=1001)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "delete_vlan", delete,
        schema=vol.Schema({
            vol.Required("entry_id"): str,
            vol.Required("vlan_id"): vol.All(vol.Coerce(int), vol.Range(min=2, max=1001)),
            vol.Required("confirmation"): str,
            vol.Optional("destination_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1001)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
