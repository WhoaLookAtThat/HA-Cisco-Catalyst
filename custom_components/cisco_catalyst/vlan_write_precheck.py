"""Pure pre-SET VLAN validation against the latest coordinator data.

This utility does not authorize writes or perform SNMP operations.
"""

from __future__ import annotations

from collections.abc import Mapping

from .port_protection import assess_port_protection
from .protected_interface_options import get_protected_interfaces
from .protected_vlan_options import configured_protected_vlans
from .const import CISCO_VM_VLAN_TYPE_STATIC

_RESERVED = frozenset(range(1002, 1006))


def assess_vlan_write_precheck(
    data: object,
    options: Mapping[str, object],
    if_index: int,
    expected_name: str,
    expected_current_vlan: int,
    target_vlan: int,
) -> tuple[str, ...]:
    """Return blockers; callers must re-evaluate after acquiring the write lock."""
    blockers: list[str] = []
    if type(if_index) is not int or if_index <= 0:
        return ("invalid_interface_index",)
    if type(target_vlan) is not int or not 1 <= target_vlan <= 4094 or target_vlan in _RESERVED:
        blockers.append("invalid_target_vlan")
    port = data.interfaces.get(if_index)
    if port is None:
        return (*blockers, "interface_missing")
    if port.name != expected_name:
        blockers.append("interface_identity_changed")
    if port.access_vlan != expected_current_vlan:
        blockers.append("current_vlan_changed")
    if port.is_trunk is not False or port.access_vlan_type != CISCO_VM_VLAN_TYPE_STATIC:
        blockers.append("access_mode_unconfirmed")
    if port.access_vlan not in data.operational_vlans or target_vlan not in data.operational_vlans:
        blockers.append("vlan_not_operational")
    try:
        protected_ports = get_protected_interfaces(dict(options))
    except (TypeError, ValueError):
        protected_ports = None
        blockers.append("invalid_port_protection")
    protection = assess_port_protection(
        data, if_index, protected_interface_names=protected_ports,
        expected_interface_name=expected_name,
    )
    blockers.extend(protection.reasons)
    try:
        protected_vlans = configured_protected_vlans(dict(options))
    except (TypeError, ValueError):
        protected_vlans = None
        blockers.append("invalid_vlan_protection")
    if protected_vlans:
        if target_vlan in protected_vlans:
            blockers.append("protected_destination_vlan")
        if port.access_vlan in protected_vlans and port.access_vlan != target_vlan:
            blockers.append("protected_current_vlan")
    return tuple(dict.fromkeys(blockers))
