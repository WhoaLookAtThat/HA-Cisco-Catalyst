"""Pure port-identity protection checks for future VLAN preflight workflows.

This module does not persist settings, authorize a write, or contact a switch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection

from .coordinator import CatalystData


@dataclass(frozen=True)
class PortProtectionDecision:
    """Fail-closed identity check against an operator-supplied policy."""

    if_index: int
    interface_name: str | None
    blocked: bool
    reasons: tuple[str, ...]


def assess_port_protection(
    data: CatalystData,
    if_index: int,
    *,
    protected_interface_names: Collection[str] | None,
    expected_interface_name: str | None = None,
) -> PortProtectionDecision:
    """Evaluate explicit interface protection without treating ifIndex as identity.

    None means the owner has not configured a protection policy yet, so
    administrative workflows must not silently proceed as if all ports were safe.
    """
    reasons: list[str] = []
    port = data.interfaces.get(if_index) if type(if_index) is int and if_index > 0 else None

    if protected_interface_names is None:
        reasons.append("protection_policy_not_configured")
    if port is None or not port.name:
        reasons.append("interface_identity_unavailable")
    elif expected_interface_name is not None and port.name != expected_interface_name:
        reasons.append("interface_identity_changed")

    if port is not None and protected_interface_names is not None:
        if port.name in protected_interface_names:
            reasons.append("protected_interface")

    return PortProtectionDecision(
        if_index=if_index,
        interface_name=port.name if port is not None else None,
        blocked=bool(reasons),
        reasons=tuple(reasons),
    )
