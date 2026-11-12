"""Standalone, explicit-port VLAN reassignment. Does not delete VLANs."""
from homeassistant.exceptions import HomeAssistantError
from .const import CISCO_VM_VLAN, CISCO_VM_VLAN_TYPE_STATIC
from .protected_interface_options import get_protected_interfaces
from .port_protection import assess_port_protection
from .vlan_write_precheck import assess_vlan_write_precheck
from .vlan_bulk_move_preview import preview_bulk_move


async def move_selected_access_ports(coordinator, options, source_vlan, destination_vlan, names):
    """Caller holds write_lock/io_lock. No automatic retry or rollback."""
    if not names or len(names) != len(set(names)):
        raise HomeAssistantError("Select one or more distinct ports")
    data = coordinator.data
    preview = preview_bulk_move(data, options, source_vlan, destination_vlan)
    if preview["request_blockers"]:
        raise HomeAssistantError("VLAN reassignment blocked: " + ", ".join(preview["request_blockers"]))
    by_name = {port.name: port for port in data.interfaces.values()}
    protected = get_protected_interfaces(options)
    selected = []
    for name in names:
        port = by_name.get(name)
        if port is None or port.access_vlan != source_vlan:
            raise HomeAssistantError(f"Port {name} does not match cached source VLAN")
        protection = assess_port_protection(
            data, port.if_index, protected_interface_names=protected,
            expected_interface_name=name,
        )
        blockers = assess_vlan_write_precheck(
            data, options, port.if_index, name, source_vlan, destination_vlan,
        )
        if (protection.blocked or blockers or port.is_trunk is not False
                or port.access_vlan_type != CISCO_VM_VLAN_TYPE_STATIC):
            raise HomeAssistantError(f"Port {name} cannot be reassigned")
        selected.append(port)
    client = coordinator.client
    # Confirm all selected ports before the first SNMP SET.
    for port in selected:
        if int(await client.get(f"{CISCO_VM_VLAN}.{port.if_index}")) != source_vlan:
            raise HomeAssistantError(
                f"{port.name} changed before execution; no ports moved"
            )
    moved = []
    for port in selected:
        oid = f"{CISCO_VM_VLAN}.{port.if_index}"
        try:
            if int(await client.get(oid)) != source_vlan:
                raise HomeAssistantError("VLAN changed just before write")
            await client.set_integer(oid, destination_vlan)
            if int(await client.get(oid)) != destination_vlan:
                raise HomeAssistantError("Write not verified")
            moved.append(port.name)
        except Exception as exc:
            raise HomeAssistantError(
                f"Bulk move stopped at {port.name}. Verified moved: "
                f"{', '.join(moved) if moved else 'none'}. "
                f"Inspect switch state before retry. Cause: {exc}"
            ) from exc
    # A second pass catches a port changing after its individual readback.
    for port in selected:
        oid = f"{CISCO_VM_VLAN}.{port.if_index}"
        try:
            actual = int(await client.get(oid))
        except Exception as exc:
            raise HomeAssistantError(
                f"Final verification unavailable for {port.name}; previously verified "
                f"moved ports: {', '.join(moved)}. Check switch state before retry. "
                f"Cause: {exc}"
            ) from exc
        if actual != destination_vlan:
            raise HomeAssistantError(
                f"Final verification mismatch on {port.name}: VLAN {actual}, "
                f"expected {destination_vlan}. Previously verified moved ports: "
                f"{', '.join(moved)}. Check switch state before retry."
            )
    return {"status": "verified", "source_vlan": source_vlan,
            "destination_vlan": destination_vlan,
            "moved_ports": moved, "moved_count": len(moved),
            "note": "Each selected port passed final VLAN readback. No VLAN was deleted."}
