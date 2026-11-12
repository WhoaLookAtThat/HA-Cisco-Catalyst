"""Read-only Home Assistant service to review a proposed switch VLAN change."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .vlan_proposal_review import review_vlan_proposal
from .vlan_review_presentation import confirmation_advice

SERVICE_REVIEW_VLAN = "review_vlan_proposal"
REVIEW_SCHEMA = vol.Schema({
    vol.Required("entry_id"): str,
    vol.Required("if_index"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Required("target_vlan"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4094)),
    vol.Required("expected_interface_name"): str,
    vol.Optional("confirmation_preference", default="balanced"): vol.In(("minimal", "balanced", "cautious")),
})


def register_vlan_review_service(hass: HomeAssistant) -> None:
    """Register one HA response-only service; do not modify switch state."""
    if hass.services.has_service(DOMAIN, SERVICE_REVIEW_VLAN):
        return

    async def review(call: ServiceCall) -> dict[str, object]:
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            raise HomeAssistantError("Cisco Catalyst configuration entry is unavailable")
        result = review_vlan_proposal(
            entry.runtime_data,
            dict(entry.options),
            call.data["if_index"],
            call.data["target_vlan"],
            expected_interface_name=call.data["expected_interface_name"],
        )
        return {**result, **confirmation_advice(result, call.data.get("confirmation_preference", "balanced"))}

    hass.services.async_register(
        DOMAIN,
        SERVICE_REVIEW_VLAN,
        review,
        schema=REVIEW_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
