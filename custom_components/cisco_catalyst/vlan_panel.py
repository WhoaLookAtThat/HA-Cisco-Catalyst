"""Register the lightweight Catalyst VLAN Management panel."""

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig

PANEL_URL = "/cisco-catalyst-vlan"
ASSET_URL = "/cisco-catalyst-vlan-assets"


async def register_vlan_panel(hass):
    """Add an admin-only Home Assistant panel without YAML edits."""
    if PANEL_URL.lstrip("/") in hass.data.get("frontend_panels", {}):
        return
    path = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths([
        StaticPathConfig(ASSET_URL, str(path), cache_headers=False)
    ])
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="cisco-catalyst-vlan-panel",
        frontend_url_path=PANEL_URL.lstrip("/"),
        sidebar_title=None,
        sidebar_icon="mdi:lan",
        module_url=f"{ASSET_URL}/cisco-catalyst-vlan-panel.js?v=0.1.4",
        require_admin=True,
    )


def unregister_vlan_panel(hass):
    """Remove the panel registration when the last entry unloads."""
    if PANEL_URL.lstrip("/") in hass.data.get("frontend_panels", {}):
        frontend.async_remove_panel(hass, PANEL_URL.lstrip("/"))
