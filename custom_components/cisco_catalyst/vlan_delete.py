"""Verified VTP VLAN deletion, optionally moving eligible access ports first."""

from pysnmp.proto.rfc1902 import Integer, OctetString
from homeassistant.exceptions import HomeAssistantError

from .const import CISCO_VM_VLAN, CISCO_VM_VLAN_TYPE_STATIC
from .protected_interface_options import get_protected_interfaces
from .protected_vlan_options import configured_protected_vlans
from .vlan_rename import BASE, STATE, EDIT, OWNER, STATUS, NAME
from .port_protection import assess_port_protection
from .vlan_write_precheck import assess_vlan_write_precheck


async def delete_vlan(coordinator, options, vlan_id, destination=None):
    """Requires caller to hold write_lock and io_lock; no automatic rollback."""
    client = coordinator.client
    if not 2 <= vlan_id <= 1001:
        raise HomeAssistantError("Only normal-range non-default VLANs can be deleted")
    data = coordinator.data
    if destination is not None:
        if destination == vlan_id or destination not in data.operational_vlans:
            raise HomeAssistantError("Destination must be a different operational VLAN")
    if int(await client.get(BASE + ".1.2.1.1.3.1")) != 2 or int(await client.get(BASE + ".1.2.1.1.11.1")) != 1:
        raise HomeAssistantError("VTP v1 server mode required")
    if int(await client.get(EDIT + ".1")) != 1 or str(await client.get(OWNER + ".1")):
        raise HomeAssistantError("VTP edit buffer busy")
    rows = await client.walk(STATE + ".1")
    state_oid = f"{STATE}.1.{vlan_id}"
    if int(rows.get(state_oid, -1)) != 1:
        raise HomeAssistantError("VLAN does not exist or is not operational")
    vlan_name = str(await client.get(f"{NAME}.1.{vlan_id}"))
    protected = get_protected_interfaces(options)
    protected_vlans = configured_protected_vlans(options)
    if protected_vlans and (vlan_id in protected_vlans or destination in protected_vlans):
        raise HomeAssistantError("Protected VLAN cannot be changed")
    # The live Cisco vmVlan table, not HA's last polling snapshot, defines
    # every member to be moved before an intentional VLAN deletion.
    live_assignments = await client.walk(CISCO_VM_VLAN)
    if not live_assignments:
        raise HomeAssistantError("Live port VLAN inventory unavailable; deletion refused")
    assigned_indexes = set()
    for oid, value in live_assignments.items():
        if oid.startswith(CISCO_VM_VLAN + ".") and int(value) == vlan_id:
            suffix = oid[len(CISCO_VM_VLAN) + 1:]
            if not suffix.isdecimal() or int(suffix) <= 0:
                raise HomeAssistantError("Invalid live switch port identity; deletion refused")
            assigned_indexes.add(int(suffix))
    if destination is None and assigned_indexes:
        raise HomeAssistantError(
            f"VLAN {vlan_id} still assigned to interfaces "
            + ", ".join(str(index) for index in sorted(assigned_indexes))
            + "; deletion refused"
        )
    # Fail closed if any live member is absent from the coordinator, or
    # its cached role/source information is no longer consistent.
    ports = []
    for index in sorted(assigned_indexes):
        port = data.interfaces.get(index)
        if port is None or port.if_index != index or port.access_vlan != vlan_id:
            raise HomeAssistantError(
                f"Live VLAN {vlan_id} member ifIndex {index} is not fully "
                "reconciled with the HA port inventory; refresh polling and "
                "inspect switch membership before retrying. No ports moved."
            )
        ports.append(port)
    moved = []
    if destination is not None:
        for port in ports:
            protection = assess_port_protection(
                data, port.if_index, protected_interface_names=protected,
                expected_interface_name=port.name,
            )
            blockers = assess_vlan_write_precheck(data, options, port.if_index, port.name, vlan_id, destination)
            if blockers or protection.blocked or port.is_trunk is not False or port.access_vlan_type != CISCO_VM_VLAN_TYPE_STATIC:
                raise HomeAssistantError(f"Cannot automatically move {port.name}")
        # Read *every* affected port before the first write, so a stale
        # assignment on a later port cannot cause preventable partial moves.
        for port in ports:
            oid = f"{CISCO_VM_VLAN}.{port.if_index}"
            if int(await client.get(oid)) != vlan_id:
                raise HomeAssistantError(
                    f"Port {port.name} VLAN changed; no ports moved; deletion aborted"
                )
        for port in ports:
            oid = f"{CISCO_VM_VLAN}.{port.if_index}"
            try:
                # Still recheck immediately before each individual write.
                if int(await client.get(oid)) != vlan_id:
                    raise HomeAssistantError(f"Port {port.name} VLAN changed")
                await client.set_integer(oid, destination)
                if int(await client.get(oid)) != destination:
                    raise HomeAssistantError(f"Port {port.name} move not verified")
                moved.append(port.name)
            except Exception as exc:
                raise HomeAssistantError(
                    f"Bulk port move stopped at {port.name}; confirmed moved ports: "
                    f"{', '.join(moved) if moved else 'none'}. "
                    f"Check switch state before retrying; deletion aborted. Cause: {exc}"
                ) from exc
    if destination is not None:
        # Crucial deletion barrier: walk ALL switch-reported assignments again,
        # including interfaces that were absent from HA's cached port list.
        final_assignments = await client.walk(CISCO_VM_VLAN)
        if not final_assignments:
            raise HomeAssistantError(
                "Final live port VLAN inventory unavailable; deletion aborted. "
                "Inspect switch state before retrying."
            )
        remaining = sorted(
            oid.rsplit(".", 1)[-1]
            for oid, value in final_assignments.items()
            if oid.startswith(CISCO_VM_VLAN + ".") and int(value) == vlan_id
        )
        if remaining:
            raise HomeAssistantError(
                f"VLAN {vlan_id} still assigned to live switch interface indexes "
                + ", ".join(remaining)
                + "; VLAN deletion aborted. "
                + ("Previously verified moves: " + ", ".join(moved) + ". " if moved else "")
                + "Inspect switch membership before retrying."
            )
    # Confirm again that no access port remains assigned after any moves.
    for port in ports:
        oid = f"{CISCO_VM_VLAN}.{port.if_index}"
        try:
            actual = int(await client.get(oid))
        except Exception as exc:
            if destination is None:
                raise
            raise HomeAssistantError(
                f"Final port check failed for {port.name}; confirmed moved ports: "
                f"{', '.join(moved) if moved else 'none'}. "
                f"Check switch state before retrying; deletion aborted. Cause: {exc}"
            ) from exc
        if destination is not None and actual != destination:
            raise HomeAssistantError(
                f"Port {port.name} has VLAN {actual}, expected {destination}; "
                f"confirmed moved ports: {', '.join(moved) if moved else 'none'}. "
                "Check switch state before retrying; deletion aborted."
            )
    acquired = False
    try:
        await client.set_multiple([(EDIT + ".1", Integer(2)), (OWNER + ".1", OctetString("HA_CATALYST"))])
        acquired = True
        if str(await client.get(OWNER + ".1")) != "HA_CATALYST":
            raise HomeAssistantError("VTP edit ownership mismatch")
        await client.set_multiple([(BASE + f".1.4.2.1.11.1.{vlan_id}", Integer(6))])
        await client.set_multiple([(EDIT + ".1", Integer(3))])
        apply_status = int(await client.get(STATUS + ".1"))
        if apply_status != 2:
            # The apply result alone cannot establish the operational state.
            # Inspect inventory once before reporting failure; do not retry writes.
            current = await client.walk(STATE + ".1")
            if state_oid in current:
                raise HomeAssistantError(
                    f"VLAN {vlan_id} remains present after apply; VTP apply status "
                    f"{apply_status} (expected 2). No automatic retry."
                )
            # A single absent inventory sample may be transient. Confirm with
            # a second fresh read before declaring the delete verified.
            confirmed = await client.walk(STATE + ".1")
            if state_oid in confirmed:
                raise HomeAssistantError(
                    f"VLAN {vlan_id} reappeared after VTP apply status "
                    f"{apply_status}; deletion not verified. No automatic retry."
                )
            return {
                "status": "verified",
                "vlan_id": vlan_id,
                "name": vlan_name,
                "moved_ports": moved,
                "note": f"Verified by two fresh VLAN inventory reads; VTP apply status was {apply_status}.",
            }
        current = await client.walk(STATE + ".1")
        if state_oid in current:
            raise HomeAssistantError("VLAN still exists after delete")
        return {"status": "verified", "vlan_id": vlan_id, "name": vlan_name, "moved_ports": moved}
    finally:
        if acquired:
            await client.set_multiple([(EDIT + ".1", Integer(4))])
