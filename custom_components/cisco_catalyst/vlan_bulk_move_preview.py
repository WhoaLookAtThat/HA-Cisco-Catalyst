"""Read-only cached-snapshot preflight for optional VLAN deletion port moves.

This module never performs SNMP I/O and never authorizes execution.
"""
from .vlan_write_precheck import assess_vlan_write_precheck
from .protected_vlan_options import configured_protected_vlans


def preview_bulk_move(data, options, source_vlan: int, target_vlan: int) -> dict:
    """Classify cached access-port assignments and list individual blockers."""
    blockers = []
    if source_vlan == target_vlan:
        blockers.append("source_equals_destination")
    if source_vlan not in data.operational_vlans:
        blockers.append("source_not_operational")
    if target_vlan not in data.operational_vlans:
        blockers.append("destination_not_operational")
    if target_vlan in range(1002, 1006):
        blockers.append("reserved_destination_vlan")
    try:
        protected_vlans = configured_protected_vlans(options)
    except (ValueError, TypeError):
        protected_vlans = None
        blockers.append("invalid_vlan_protection")
    if protected_vlans:
        if source_vlan in protected_vlans:
            blockers.append("protected_source_vlan")
        if target_vlan in protected_vlans:
            blockers.append("protected_destination_vlan")
    ports = []
    for port in sorted(data.interfaces.values(), key=lambda p: p.name):
        if port.access_vlan != source_vlan:
            continue
        reasons = list(assess_vlan_write_precheck(
            data, options, port.if_index, port.name, source_vlan, target_vlan,
        ))
        reasons.extend(blockers)
        ports.append({
            "name": port.name, "if_index": port.if_index,
            "eligible": not reasons, "blockers": reasons,
        })
    eligible = sum(row["eligible"] for row in ports)
    return {
        "source_vlan": source_vlan, "destination_vlan": target_vlan,
        "snapshot_only": True, "ports": ports,
        "eligible_count": eligible, "blocked_count": len(ports) - eligible,
        "all_eligible": not blockers and eligible == len(ports),
        "request_blockers": blockers,
        "note": "Cached polling snapshot only. Recheck every port under locks before execution. "
                "No SNMP request or switch change was made.",
    }
