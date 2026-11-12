"""Read-only, conservative preflight for a proposed static access VLAN change.

No SNMP calls, authorization, or configuration writes occur here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .const import CISCO_VM_VLAN_TYPE_STATIC
from .coordinator import CatalystData
from .mac_movement import MacMovementTracker

_RESERVED = frozenset(range(1002, 1006))


@dataclass(frozen=True)
class VlanPreflight:
    """Advisory assessment, never an authorization or mutation result."""

    if_index: int
    interface_name: str | None
    current_vlan: int | None
    requested_vlan: int
    status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    path_type: str
    protected: bool

    def as_dict(self) -> dict:
        return {
            "if_index": self.if_index,
            "interface_name": self.interface_name,
            "current_vlan": self.current_vlan,
            "requested_vlan": self.requested_vlan,
            "status": self.status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "path_type": self.path_type,
            "protected": self.protected,
            "read_only": True,
        }


def assess_vlan_change(
    data: CatalystData,
    if_index: int,
    requested_vlan: int,
    *,
    write_enabled: bool = False,
    protected_if_indexes: Iterable[int] = (),
) -> VlanPreflight:
    """Assess only known switch facts; never infer that a port is safe."""

    blockers: list[str] = []
    warnings: list[str] = []
    port = data.interfaces.get(if_index)
    protected = if_index in protected_if_indexes
    if type(if_index) is not int or if_index <= 0:
        blockers.append("invalid_interface_index")
    path_type = MacMovementTracker.classify_path(port) if port else "unknown"

    if not write_enabled:
        blockers.append("read_only_credentials")
    if protected:
        blockers.append("protected_port")
    if type(requested_vlan) is not int or not 1 <= requested_vlan <= 4094 or requested_vlan in _RESERVED:
        blockers.append("invalid_or_reserved_vlan")
    elif requested_vlan not in data.operational_vlans:
        blockers.append("destination_not_operational")

    if port is None:
        blockers.append("interface_not_found")
    else:
        if port.is_trunk is not False:
            blockers.append("access_mode_unconfirmed_or_trunk")
        if port.access_vlan is None or port.access_vlan_type != CISCO_VM_VLAN_TYPE_STATIC:
            blockers.append("static_membership_unconfirmed")
        if port.access_vlan is not None and port.access_vlan not in data.operational_vlans:
            blockers.append("current_vlan_not_operational")
        if path_type == "infrastructure":
            warnings.append("downstream_infrastructure_evidence")
        elif path_type == "unknown":
            warnings.append("topology_unverified")
        else:
            warnings.append("edge_evidence_not_proof_of_safety")
        if port.access_vlan == requested_vlan:
            warnings.append("already_assigned")
        if port.oper_status == 1:
            warnings.append("active_link_may_be_disrupted")

    # Even a technically eligible port still requires independent protection,
    # authority, topology and user confirmation gates before future writes.
    status = "blocked" if blockers else "requires_operator_review"
    return VlanPreflight(
        if_index=if_index,
        interface_name=port.name if port else None,
        current_vlan=port.access_vlan if port else None,
        requested_vlan=requested_vlan,
        status=status,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        path_type=path_type,
        protected=protected,
    )
