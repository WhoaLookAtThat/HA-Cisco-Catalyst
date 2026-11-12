"""Rename an existing normal-range VLAN with Cisco's VTP edit buffer."""

from pysnmp.proto.rfc1902 import Integer, OctetString

from .vlan_creation import validate_vlan_creation_request

BASE = "1.3.6.1.4.1.9.9.46"
STATE = BASE + ".1.3.1.1.2"
NAME = BASE + ".1.3.1.1.4"
EDIT = BASE + ".1.4.1.1.1"
OWNER = BASE + ".1.4.1.1.3"
STATUS = BASE + ".1.4.1.1.2"
EDIT_NAME = BASE + ".1.4.2.1.4"


async def rename_vlan(client, vlan_id: int, name: str, *, domain: int = 1):
    """Copy, modify only the name, apply, verify and release."""
    validate_vlan_creation_request(vlan_id, name)
    if not 2 <= vlan_id <= 1001:
        raise ValueError("Only normal-range non-default VLANs may be renamed")
    if int(await client.get(BASE + f".1.2.1.1.3.{domain}")) != 2:
        raise ValueError("VTP server mode is required")
    if int(await client.get(BASE + f".1.2.1.1.11.{domain}")) != 1:
        raise ValueError("Only verified VTP v1 is supported")
    if int(await client.get(f"{EDIT}.{domain}")) != 1 or str(await client.get(f"{OWNER}.{domain}")):
        raise ValueError("VTP edit buffer is busy")
    oid = f"{NAME}.{domain}.{vlan_id}"
    states = await client.walk(STATE + f".{domain}")
    if int(states.get(f"{STATE}.{domain}.{vlan_id}", -1)) != 1:
        raise ValueError("VLAN is not present and operational")
    current = await client.get(oid)
    if str(current) == name:
        raise ValueError("VLAN already has that name")
    acquired = False
    try:
        await client.set_multiple([
            (f"{EDIT}.{domain}", Integer(2)),
            (f"{OWNER}.{domain}", OctetString("HA_CATALYST")),
        ])
        acquired = True
        if str(await client.get(f"{OWNER}.{domain}")) != "HA_CATALYST":
            raise RuntimeError("VTP edit ownership mismatch")
        await client.set_multiple([(f"{EDIT_NAME}.{domain}.{vlan_id}", OctetString(name))])
        await client.set_multiple([(f"{EDIT}.{domain}", Integer(3))])
        apply_status = int(await client.get(f"{STATUS}.{domain}"))
        observed = str(await client.get(oid))
        if observed != name:
            raise RuntimeError(
                f"VLAN rename not verified: read back {observed!r}, "
                f"expected {name!r}; VTP apply status {apply_status}"
            )
        # The VTP status may already have returned to idle (1) even though
        # the rename applied. Require a second authoritative name read.
        confirmed = str(await client.get(oid))
        if confirmed != name:
            raise RuntimeError(
                f"VLAN rename not verified: inconsistent readback "
                f"{confirmed!r}; VTP apply status {apply_status}"
            )
        return {"status": "verified", "vlan_id": vlan_id, "name": name}
    finally:
        if acquired:
            await client.set_multiple([(f"{EDIT}.{domain}", Integer(4))])
