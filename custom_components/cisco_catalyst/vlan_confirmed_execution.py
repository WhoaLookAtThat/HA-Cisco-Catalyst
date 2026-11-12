"""Explicitly acknowledged VLAN execution; no implicit authorization from reviews."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError

from .const import CISCO_VM_VLAN
from .vlan_proposal_review import review_vlan_proposal
from .vlan_write_precheck import assess_vlan_write_precheck
from .write import async_write_with_readback


async def execute_confirmed_vlan_change(
    coordinator, options: dict, if_index: int, expected_interface_name: str,
    expected_current_vlan: int, target_vlan: int, *, acknowledged: bool,
) -> dict[str, object]:
    """Write only after an explicit acknowledgment and fresh final checks."""
    if acknowledged is not True:
        raise HomeAssistantError("Explicit VLAN change acknowledgment is required")
    if not coordinator.write_enabled:
        raise HomeAssistantError("Read/write switch credentials are required")
    if type(expected_current_vlan) is not int or type(target_vlan) is not int:
        raise HomeAssistantError("VLAN IDs must be integers")
    if type(if_index) is not int or if_index <= 0 or not expected_interface_name:
        raise HomeAssistantError("Valid physical port identity is required")

    def current_review():
        result = review_vlan_proposal(
            coordinator, options, if_index, target_vlan,
            expected_interface_name=expected_interface_name,
        )
        if result.get("status") != "requires_operator_review" or result.get("blockers"):
            raise HomeAssistantError(
                "VLAN proposal review blocked: " + ", ".join(result.get("blockers", []))
            )
        if result.get("current_vlan") != expected_current_vlan:
            raise HomeAssistantError("VLAN changed since review; review the port again")

    current_review()
    oid = f"{CISCO_VM_VLAN}.{if_index}"

    async def verify_before_set() -> None:
        # Called with both the write and I/O locks held by the shared helper.
        current_review()
        blockers = assess_vlan_write_precheck(
            coordinator.data, options, if_index, expected_interface_name,
            expected_current_vlan, target_vlan,
        )
        if blockers:
            raise HomeAssistantError("VLAN write blocked: " + ", ".join(blockers))
        try:
            actual = int(await coordinator.client.get(oid))
        except Exception as err:
            raise HomeAssistantError("Cannot read current VLAN before change") from err
        if actual != expected_current_vlan:
            raise HomeAssistantError("Actual VLAN changed; review the port again")

    def apply_verified():
        port = coordinator.data.interfaces.get(if_index)
        if port is not None and port.name == expected_interface_name:
            port.access_vlan = target_vlan

    await async_write_with_readback(
        coordinator, oid, target_vlan,
        writer=coordinator.client.set_integer,
        normalize_readback=int,
        pre_write_check=verify_before_set,
        apply_verified_state=apply_verified,
        expected_state=lambda: (
            (port := coordinator.data.interfaces.get(if_index)) is not None
            and port.name == expected_interface_name and port.access_vlan == target_vlan
        ),
    )
    return {
        "status": "verified",
        "interface_name": expected_interface_name,
        "if_index": if_index,
        "previous_vlan": expected_current_vlan,
        "requested_vlan": target_vlan,
        "verified": True,
    }
