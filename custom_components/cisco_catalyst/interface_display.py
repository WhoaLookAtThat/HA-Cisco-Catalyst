"""Display-only Cisco interface abbreviations.

Never use these labels for SNMP OIDs, entity IDs, configured protection rules,
or interface identity checks: those must retain the original full names.
"""
import re

_PREFIXES = {
    "GigabitEthernet": "Gi",
    "TenGigabitEthernet": "Te",
    "FortyGigabitEthernet": "Fo",
    "TwentyFiveGigE": "Twe",
}
_PREFIX = re.compile(
    r"^(GigabitEthernet|TenGigabitEthernet|FortyGigabitEthernet|TwentyFiveGigE)(?=\d)"
)


def short_interface_name(name: str) -> str:
    """Shorten known physical Ethernet interface prefixes only."""
    return _PREFIX.sub(lambda match: _PREFIXES[match.group(1)], name)
