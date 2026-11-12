"""Compose stored owner protection settings with read-only VLAN preflight."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

from .vlan_preflight_freshness import assess_snapshot_freshness

from .coordinator import CatalystData
from .port_protection import assess_port_protection
from .protected_interface_options import get_protected_interfaces
from .protected_vlan_options import configured_protected_vlans
from .vlan_preflight import VlanPreflight, assess_vlan_change
from .vlan_preflight_messages import explain_preflight


def assess_configured_vlan_change(
    data: CatalystData,
    options: Mapping[str, object],
    if_index: int,
    requested_vlan: int,
    *,
    write_enabled: bool = False,
    expected_interface_name: str | None = None,
) -> dict[str, object]:
    """Advisory composition. Never mutates a switch or grants write approval."""
    try:
        policy = get_protected_interfaces(dict(options))
    except (ValueError, TypeError):
        policy = None  # Malformed stored options always fail closed.

    identity = assess_port_protection(
        data,
        if_index,
        protected_interface_names=policy,
        expected_interface_name=expected_interface_name,
    )
    basic: VlanPreflight = assess_vlan_change(
        data,
        if_index,
        requested_vlan,
        write_enabled=write_enabled,
    )
    result = explain_preflight(basic)
    reasons = list(identity.reasons)
    messages = {
        "protection_policy_not_configured": "Protected-interface settings have not been configured.",
        "interface_identity_unavailable": "The physical port identity cannot be confirmed.",
        "interface_identity_changed": "The port identity changed since the proposal was prepared.",
        "protected_interface": "This physical port is explicitly protected.",
    }
    if reasons:
        result["status"] = "blocked"
        result["summary"] = "Blocked: the proposed VLAN change fails protection checks."
        result["blockers"] = [*result["blockers"], *reasons]
        result["blocker_messages"] = [
            *result["blocker_messages"],
            *(messages.get(reason, "Unknown protection issue; stop.") for reason in reasons),
        ]
    # Additional administrator-designated VLAN policy, independent of port protection.
    try:
        protected_vlans = configured_protected_vlans(dict(options))
    except (ValueError, TypeError):
        result["status"] = "blocked"
        result["summary"] = "Blocked: protected VLAN settings are invalid."
        result["blockers"] = [*result["blockers"], "invalid_protected_vlan_policy"]
        result["blocker_messages"] = [
            *result["blocker_messages"],
            "Protected VLAN settings are malformed; correct them before proceeding.",
        ]
    else:
        if protected_vlans:
            port = data.interfaces.get(if_index)
            vlan_reasons = []
            if requested_vlan in protected_vlans:
                vlan_reasons.append("protected_destination_vlan")
            if (
                port is not None
                and port.access_vlan in protected_vlans
                and port.access_vlan != requested_vlan
            ):
                vlan_reasons.append("protected_current_vlan")
            if vlan_reasons:
                result["status"] = "blocked"
                result["summary"] = "Blocked: the proposal involves an administrator-protected VLAN."
                result["blockers"] = [*result["blockers"], *vlan_reasons]
                descriptions = {
                    "protected_destination_vlan": "The requested destination VLAN is administrator-protected.",
                    "protected_current_vlan": "The current port VLAN is administrator-protected.",
                }
                result["blocker_messages"] = [
                    *result["blocker_messages"],
                    *(descriptions[reason] for reason in vlan_reasons),
                ]
    result["protected_vlan"] = any(
        reason in result["blockers"]
        for reason in ("protected_destination_vlan", "protected_current_vlan")
    )
    result["protected"] = "protected_interface" in reasons
    result["authorized"] = False
    result["read_only"] = True
    return result


def assess_fresh_configured_vlan_change(
    data: CatalystData,
    options: Mapping[str, object],
    if_index: int,
    requested_vlan: int,
    *,
    observed_at: datetime | None,
    now: datetime,
    update_succeeded: bool,
    write_enabled: bool = False,
    expected_interface_name: str | None = None,
    max_age: timedelta = timedelta(minutes=5),
) -> dict[str, object]:
    """Require confirmed fresh observations in addition to other read-only gates."""
    result = assess_configured_vlan_change(
        data, options, if_index, requested_vlan,
        write_enabled=write_enabled,
        expected_interface_name=expected_interface_name,
    )
    freshness = assess_snapshot_freshness(
        observed_at, now, update_succeeded=update_succeeded, max_age=max_age
    )
    if freshness.blocked:
        result["status"] = "blocked"
        result["summary"] = "Blocked: switch observations are missing, failed, or outdated."
        result["blockers"] = [*result["blockers"], *freshness.reasons]
        messages = {
            "coordinator_update_failed": "The most recent switch data refresh failed.",
            "snapshot_timestamp_unavailable": "A trustworthy switch observation time is unavailable.",
            "snapshot_timestamp_in_future": "The switch observation time is unexpectedly in the future.",
            "snapshot_too_old": "Switch information is too old to review this change.",
            "invalid_maximum_age": "The safety freshness threshold is invalid.",
        }
        result["blocker_messages"] = [
            *result["blocker_messages"],
            *(messages.get(reason, "Unknown observation problem; stop.") for reason in freshness.reasons),
        ]
    result["snapshot_age_seconds"] = freshness.age_seconds
    result["authorized"] = False
    result["read_only"] = True
    return result
