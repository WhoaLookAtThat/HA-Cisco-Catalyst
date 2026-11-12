"""Require an authenticated Home Assistant administrator for VLAN writes."""

from homeassistant.exceptions import HomeAssistantError


async def require_vlan_admin(hass, call):
    context = getattr(call, "context", None)
    user_id = getattr(context, "user_id", None)
    if not user_id:
        raise HomeAssistantError("An authenticated Home Assistant administrator is required")
    user = await hass.auth.async_get_user(user_id)
    if user is None or not user.is_admin:
        raise HomeAssistantError("VLAN management requires a Home Assistant administrator")
