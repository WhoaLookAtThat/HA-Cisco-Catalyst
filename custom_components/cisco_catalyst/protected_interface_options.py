"""Validate operator-configured protected physical interface names."""

from __future__ import annotations

import re

OPTION_PROTECTED_INTERFACES = "protected_interfaces"
_PHYSICAL_NAME = re.compile(
    r"^(?:GigabitEthernet|TenGigabitEthernet|TwentyFiveGigE|FortyGigabitEthernet)"
    r"\d+/\d+/\d+$"
)


def parse_protected_interfaces(value: object) -> frozenset[str]:
    """Strict parser; absent option is not an empty policy."""
    if not isinstance(value, str):
        raise ValueError("Protected ports must be comma-separated Cisco interface names")
    parts = [part.strip() for part in value.split(",")]
    if len(parts) == 1 and not parts[0]:
        return frozenset()
    if any(not _PHYSICAL_NAME.fullmatch(part) for part in parts):
        raise ValueError("Specify full physical interface names separated by commas")
    if len(parts) != len(set(parts)):
        raise ValueError("Duplicate interface names are not permitted")
    return frozenset(parts)


def get_protected_interfaces(options: dict) -> frozenset[str] | None:
    """None denotes missing policy, distinct from explicitly configured empty."""
    if OPTION_PROTECTED_INTERFACES not in options:
        return None
    return parse_protected_interfaces(options[OPTION_PROTECTED_INTERFACES])
