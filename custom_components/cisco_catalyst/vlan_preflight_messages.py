"""Human-readable, stable descriptions for read-only VLAN preflight outcomes."""

from __future__ import annotations

from .vlan_preflight import VlanPreflight

BLOCKER_MESSAGES = {
    "read_only_credentials": "The integration is configured for read-only access.",
    "protected_port": "This port is explicitly protected from VLAN changes.",
    "invalid_interface_index": "The interface identifier is invalid.",
    "invalid_or_reserved_vlan": "The destination VLAN ID is invalid or reserved.",
    "destination_not_operational": "The destination VLAN is not currently operational on the switch.",
    "interface_not_found": "The requested physical interface is missing from the latest known switch data.",
    "access_mode_unconfirmed_or_trunk": "The port is a trunk or its access mode cannot be confirmed.",
    "static_membership_unconfirmed": "Static access-VLAN membership cannot be confirmed.",
    "current_vlan_not_operational": "The current VLAN is not in the discovered operational VLAN inventory.",
}

WARNING_MESSAGES = {
    "downstream_infrastructure_evidence": "Topology suggests downstream infrastructure may depend on this port.",
    "topology_unverified": "There is insufficient topology evidence to identify the attached path.",
    "edge_evidence_not_proof_of_safety": "This looks like an endpoint port, but that does not prove it is safe to change.",
    "already_assigned": "The requested VLAN is already assigned to this port.",
    "active_link_may_be_disrupted": "The port has an active link; a VLAN change may interrupt connectivity.",
}


def explain_preflight(result: VlanPreflight) -> dict[str, object]:
    """Describe an advisory assessment without implying write authorization."""
    return {
        **result.as_dict(),
        "summary": (
            "Blocked: the proposal fails one or more checks."
            if result.status == "blocked"
            else "Requires administrator review. This is not approval to modify the port."
        ),
        "blocker_messages": [
            BLOCKER_MESSAGES.get(code, f"Unrecognized blocker ({code}); do not proceed.")
            for code in result.blockers
        ],
        "warning_messages": [
            WARNING_MESSAGES.get(code, f"Unrecognized warning ({code}); inspect before proceeding.")
            for code in result.warnings
        ],
        "authorized": False,
    }
