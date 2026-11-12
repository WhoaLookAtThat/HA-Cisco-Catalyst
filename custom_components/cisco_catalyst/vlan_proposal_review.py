"""Read-only VLAN proposal review using real HA coordinator observation status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .vlan_preflight_policy import assess_fresh_configured_vlan_change

if TYPE_CHECKING:
    from .coordinator import CatalystCoordinator


def review_vlan_proposal(
    coordinator: CatalystCoordinator,
    options: dict[str, Any],
    if_index: int,
    target_vlan: int,
    *,
    expected_interface_name: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Evaluate observed facts; no refresh, SNMP SET, or authorization."""
    moment = now if now is not None else datetime.now(timezone.utc)
    return assess_fresh_configured_vlan_change(
        coordinator.data,
        options,
        if_index,
        target_vlan,
        observed_at=coordinator.last_successful_poll_at,
        now=moment,
        update_succeeded=bool(coordinator.last_update_success),
        write_enabled=coordinator.write_enabled,
        expected_interface_name=expected_interface_name,
    )
