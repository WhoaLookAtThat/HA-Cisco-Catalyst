"""Validate administrator-defined protected VLAN IDs without switch writes."""

from __future__ import annotations

OPTION_PROTECTED_VLANS = "protected_vlans"
_RESERVED = frozenset(range(1002, 1006))


def parse_protected_vlans(value: object) -> frozenset[int]:
    """Require explicit comma-separated decimal VLAN IDs; reject ambiguity."""
    if not isinstance(value, str):
        raise ValueError("Protected VLANs must be comma-separated IDs")
    if not value.strip():
        return frozenset()
    parts = [part.strip() for part in value.split(",")]
    if any(not part.isascii() or not part.isdecimal() or str(int(part)) != part for part in parts):
        raise ValueError("Use whole decimal VLAN IDs without signs or leading zeros")
    vlans = [int(part) for part in parts]
    if any(not 1 <= vlan <= 4094 or vlan in _RESERVED for vlan in vlans):
        raise ValueError("Protected VLAN ID is invalid or reserved")
    if len(set(vlans)) != len(vlans):
        raise ValueError("Duplicate protected VLAN IDs are not permitted")
    return frozenset(vlans)


def configured_protected_vlans(options: dict) -> frozenset[int] | None:
    """Distinguish an unset policy from an intentionally empty policy."""
    if OPTION_PROTECTED_VLANS not in options:
        return None
    return parse_protected_vlans(options[OPTION_PROTECTED_VLANS])
