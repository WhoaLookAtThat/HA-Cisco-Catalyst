"""Pure, read-only prerequisite checks for explicit VLAN creation.

No SNMP writes occur in this module. Unsupported switch/VTP capabilities must
be established from fresh authoritative evidence before an execution path exists.
"""

from __future__ import annotations

import re

_RESERVED = frozenset(range(1002, 1006))
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def validate_vlan_creation_request(vlan_id: object, name: object | None = None) -> tuple[int, str | None]:
    """Validate the request without changing switch state.

    A separate capability gate must further restrict platform-supported ranges.
    """
    if isinstance(vlan_id, bool) or not isinstance(vlan_id, int):
        raise ValueError("VLAN ID must be an integer")
    if not 1 <= vlan_id <= 4094 or vlan_id in _RESERVED:
        raise ValueError("VLAN ID is outside the supported non-reserved range")
    if name is not None:
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError("VLAN name must contain 1–32 ASCII letters, digits, underscores or hyphens")
    return vlan_id, name


def evaluate_vlan_creation(
    vlan_id: object,
    name: object | None,
    *,
    existing_vlan_ids: set[int] | None,
    vtp_mode: str | None,
    creation_supported: bool,
    read_write_enabled: bool,
    protected_vlan_ids: set[int] | None,
) -> dict[str, object]:
    """Fail closed on missing inventory, unknown VTP mode or SNMP capability.

    This is advisory preflight, *not* a grant to perform an SNMP SET.
    """
    blockers: list[str] = []
    try:
        normalized_id, normalized_name = validate_vlan_creation_request(vlan_id, name)
    except ValueError as exc:
        return {"allowed": False, "blockers": [str(exc)], "vlan_id": vlan_id, "name": name}

    if existing_vlan_ids is None:
        blockers.append("Current VLAN inventory is unavailable")
    elif normalized_id in existing_vlan_ids:
        blockers.append("VLAN already exists")
    if protected_vlan_ids is None:
        blockers.append("Protected VLAN policy is unavailable")
    elif normalized_id in protected_vlan_ids:
        blockers.append("VLAN is protected")
    if not read_write_enabled:
        blockers.append("Read/write credentials are required")
    if normalized_id > 1001:
        blockers.append("VLAN exceeds the verified VTP v1 local normal-range limit (1001)")
    if not creation_supported:
        blockers.append("VLAN creation support has not been verified")
    if vtp_mode not in ("server", "transparent"):
        blockers.append("VTP mode does not authorize VLAN creation")
    return {
        "allowed": not blockers,
        "blockers": blockers,
        "vlan_id": normalized_id,
        "name": normalized_name,
    }


# CISCO-VTP-MIB numeric OIDs. See Cisco SNMP VLAN edit-buffer procedure.
_VTP_BASE = "1.3.6.1.4.1.9.9.46.1.4"
_EDIT_OPERATION = f"{_VTP_BASE}.1.1.1"
_EDIT_OWNER = f"{_VTP_BASE}.1.1.3"
_APPLY_STATUS = f"{_VTP_BASE}.1.1.2"
_ROW_TYPE = f"{_VTP_BASE}.2.1.3"
_ROW_NAME = f"{_VTP_BASE}.2.1.4"
_ROW_SAID = f"{_VTP_BASE}.2.1.6"
_ROW_STATUS = f"{_VTP_BASE}.2.1.11"


def vlan_create_varbind_plan(
    management_domain_index: int,
    vlan_id: int,
    name: str,
    owner: str,
) -> dict[str, object]:
    """Build a typed, non-executing SNMP VLAN edit-buffer plan.

    Values are pairs of ('integer', int) or ('octets', bytes). The caller
    must check fresh switch capabilities and buffer ownership, serialize the
    entire transaction, and explicitly authorize any actual SNMP SET.
    """
    validate_vlan_creation_request(vlan_id, name)
    if isinstance(management_domain_index, bool) or not isinstance(management_domain_index, int) or management_domain_index < 1:
        raise ValueError("A discovered positive management domain index is required")
    if not isinstance(name, str) or not name:
        raise ValueError("A VLAN name is required for the MIB row")
    if not isinstance(owner, str) or not 1 <= len(owner) <= 64 or not _NAME.fullmatch(owner):
        raise ValueError("A short explicit edit-buffer owner identifier is required")
    domain = str(management_domain_index)
    row = f"{domain}.{vlan_id}"
    return {
        "copy": [
            (f"{_EDIT_OPERATION}.{domain}", ("integer", 2)),
            (f"{_EDIT_OWNER}.{domain}", ("octets", owner.encode("ascii"))),
        ],
        "row": [
            (f"{_ROW_STATUS}.{row}", ("integer", 4)),
            (f"{_ROW_TYPE}.{row}", ("integer", 1)),
            (f"{_ROW_NAME}.{row}", ("octets", name.encode("ascii"))),
            (f"{_ROW_SAID}.{row}", ("octets", (100000 + vlan_id).to_bytes(4, "big"))),
        ],
        "apply": [(f"{_EDIT_OPERATION}.{domain}", ("integer", 3))],
        "apply_status_oid": f"{_APPLY_STATUS}.{domain}",
        "release": [(f"{_EDIT_OPERATION}.{domain}", ("integer", 4))],
    }

# Read-only management-domain/VTP observation.  Values must originate from
# fresh SNMP walks; an empty or ambiguous result never authorizes a write.
_VTP_DOMAIN_MODE = "1.3.6.1.4.1.9.9.46.1.2.1.1.3"
_VTP_DOMAIN_NAME = "1.3.6.1.4.1.9.9.46.1.2.1.1.2"
_VTP_EDIT_BUFFER_OWNER = "1.3.6.1.4.1.9.9.46.1.4.1.1.3"
_VTP_MODE = {1: "client", 2: "server", 3: "transparent", 4: "off"}


def evaluate_vtp_domain_observation(
    modes: dict[str, object],
    names: dict[str, object],
    owners: dict[str, object],
) -> dict[str, object]:
    """Summarize discovered domain evidence; no SNMP SETs or guessed defaults."""
    entries = []
    for oid, raw_mode in modes.items():
        prefix = _VTP_DOMAIN_MODE + "."
        if not oid.startswith(prefix):
            continue
        suffix = oid[len(prefix):]
        if not suffix.isdecimal() or int(suffix) < 1:
            continue
        try:
            mode = _VTP_MODE.get(int(raw_mode))
        except (TypeError, ValueError, OverflowError):
            mode = None
        raw_name = names.get(_VTP_DOMAIN_NAME + "." + suffix)
        raw_owner = owners.get(_VTP_EDIT_BUFFER_OWNER + "." + suffix)
        entries.append({
            "domain_index": int(suffix),
            "mode": mode,
            "name_present": raw_name is not None,
            "edit_buffer_empty": raw_owner == "" or raw_owner == b"",
        })
    if len(entries) != 1:
        return {"ready": False, "reason": "Exactly one verified VTP domain is required", "domains": entries}
    domain = entries[0]
    ready = domain["mode"] in ("server", "transparent") and domain["name_present"] and domain["edit_buffer_empty"]
    return {"ready": bool(ready), "reason": None if ready else "VTP mode, domain identity, or edit-buffer state is not verified", "domains": entries}

# Cisco MIB: VTP version 3 VLAN edits require the VLAN-database *primary*
# server. Do not infer that status from server(2) mode alone.
_VTP_DOMAIN_VERSION = "1.3.6.1.4.1.9.9.46.1.2.1.1.11"


def check_vlan_creation_authority(
    domain_observation: dict[str, object],
    versions: dict[str, object],
    *,
    vtp3_vlan_primary_verified: bool = False,
    mib_write_support_verified: bool = False,
) -> dict[str, object]:
    """Additional advisory gate; no SNMP writes and no authorization token."""
    blockers: list[str] = []
    domains = domain_observation.get("domains", [])
    if not domain_observation.get("ready") or len(domains) != 1:
        blockers.append("VTP domain observation is incomplete")
    else:
        domain = domains[0]
        oid = f"{_VTP_DOMAIN_VERSION}.{domain['domain_index']}"
        try:
            version = int(versions[oid]) if not isinstance(versions[oid], bool) else None
        except (KeyError, TypeError, ValueError, OverflowError):
            version = None
        if version in (1, 2):
            if domain["mode"] != "server":
                blockers.append("VTP version 1/2 VLAN edits require server mode")
        elif version == 4:
            if domain["mode"] != "server" or not vtp3_vlan_primary_verified:
                blockers.append("VTP version 3 requires verified primary VLAN server authority")
        else:
            blockers.append("VTP version is unknown or unsupported")
    if not mib_write_support_verified:
        blockers.append("Writable VLAN edit MIB support remains unverified")
    return {"eligible": not blockers, "blockers": blockers}



async def execute_vlan_creation(client, vlan_id: int, name: str, *, domain: int = 1) -> dict[str, object]:
    """Use the verified VTP MIB transaction; caller provides serialization."""
    from pysnmp.proto.rfc1902 import Integer, OctetString

    validate_vlan_creation_request(vlan_id, name)
    if not 2 <= vlan_id <= 1001:
        raise ValueError("VTP v1 VLAN ID must be between 2 and 1001")
    plan = vlan_create_varbind_plan(domain, vlan_id, name, "HA_CATALYST")
    def typed(bindings):
        return [(oid, Integer(value) if kind == "integer" else OctetString(value))
                for oid, (kind, value) in bindings]
    owner_oid = f"{_EDIT_OWNER}.{domain}"
    operation_oid = f"{_EDIT_OPERATION}.{domain}"
    domain_mode_oid = f"1.3.6.1.4.1.9.9.46.1.2.1.1.3.{domain}"
    domain_version_oid = f"1.3.6.1.4.1.9.9.46.1.2.1.1.11.{domain}"
    if int(await client.get(domain_mode_oid)) != 2 or int(await client.get(domain_version_oid)) != 1:
        raise ValueError("VLAN creation requires VTP v1 server mode")
    if str(await client.get(owner_oid)) or int(await client.get(operation_oid)) != 1:
        raise ValueError("VTP edit buffer is busy")
    state_oid = f"1.3.6.1.4.1.9.9.46.1.3.1.1.2.{domain}.{vlan_id}"
    inventory = await client.walk(f"1.3.6.1.4.1.9.9.46.1.3.1.1.2.{domain}")
    if state_oid in inventory or state_oid.lstrip(".") in inventory:
        raise ValueError("VLAN already exists")
    acquired = False
    try:
        await client.set_multiple(typed(plan["copy"]))
        acquired = True
        if str(await client.get(owner_oid)) != "HA_CATALYST":
            raise RuntimeError("Edit buffer ownership mismatch")
        await client.set_multiple(typed(plan["row"]))
        await client.set_multiple(typed(plan["apply"]))
        if int(await client.get(plan["apply_status_oid"])) != 2:
            # Some switches report a failed apply even when the VLAN is now
            # operational. Reconcile against exact ID and name before reporting
            # success; a state-only match is insufficient.
            name_oid = f"1.3.6.1.4.1.9.9.46.1.3.1.1.4.{domain}.{vlan_id}"
            try:
                observed_state = int(await client.get(state_oid))
                observed_name = str(await client.get(name_oid))
            except Exception:
                observed_state, observed_name = None, None
            if observed_state != 1 or observed_name != name:
                raise RuntimeError("VTP VLAN apply failed; creation outcome unverified")
            return {"status": "verified", "vlan_id": vlan_id, "name": name,
                    "reconciled_after_apply_error": True}
        if int(await client.get(state_oid)) != 1:
            raise RuntimeError("VLAN creation not verified")
        return {"status": "verified", "vlan_id": vlan_id, "name": name}
    finally:
        if acquired:
            await client.set_multiple(typed(plan["release"]))
