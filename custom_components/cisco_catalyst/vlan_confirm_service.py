"""Explicit confirmed Home Assistant action for one access VLAN change."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .vlan_confirmed_execution import execute_confirmed_vlan_change

SERVICE_CONFIRM_VLAN = "confirm_vlan_change"
CONFIRM_SCHEMA = vol.Schema({
    vol.Required("entry_id"): str,
    vol.Required("if_index"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Required("expected_interface_name"): str,
    vol.Required("expected_current_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4094)),
    vol.Required("target_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4094)),
    vol.Required("acknowledged"): bool,
})


def register_confirm_vlan_service(hass: HomeAssistant) -> None:
    """Register explicit, response-only confirmed execution action."""
    if hass.services.has_service(DOMAIN, SERVICE_CONFIRM_VLAN):
        return

    async def confirm(call: ServiceCall) -> dict[str, object]:
        if call.data["acknowledged"] is not True:
            raise HomeAssistantError("Explicit acknowledgment is required")
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry is unavailable")
        return await execute_confirmed_vlan_change(
            entry.runtime_data,
            dict(entry.options),
            call.data["if_index"],
            call.data["expected_interface_name"],
            call.data["expected_current_vlan"],
            call.data["target_vlan"],
            acknowledged=True,
        )

    hass.services.async_register(
        DOMAIN, SERVICE_CONFIRM_VLAN, confirm,
        schema=CONFIRM_SCHEMA, supports_response=SupportsResponse.ONLY,
    )
