"""Guarded single-port recovery from an inactive access VLAN."""
from homeassistant.exceptions import HomeAssistantError
from .const import CISCO_VM_VLAN, CISCO_VM_VLAN_TYPE_STATIC
from .port_protection import assess_port_protection
from .protected_interface_options import get_protected_interfaces
from .protected_vlan_options import configured_protected_vlans
from .vlan_rename import STATE

async def recover_orphaned_port(coordinator, options, if_index, expected_name, source_vlan, destination_vlan):
    """Caller holds write_lock and io_lock. Never retry or roll back a write."""
    data = coordinator.data
    port = data.interfaces.get(if_index)
    if port is None or port.name != expected_name:
        raise HomeAssistantError("Recovery blocked: port identity changed")
    if port.access_vlan != source_vlan or source_vlan in data.operational_vlans:
        raise HomeAssistantError("Recovery blocked: source is not a confirmed inactive VLAN")
    if destination_vlan not in data.operational_vlans or destination_vlan == source_vlan:
        raise HomeAssistantError("Recovery blocked: destination VLAN is not operational")
    if not (1 <= destination_vlan <= 1001):
        raise HomeAssistantError("Recovery blocked: destination outside permitted Ethernet VLAN range")
    if port.is_trunk is not False or port.access_vlan_type != CISCO_VM_VLAN_TYPE_STATIC:
        raise HomeAssistantError("Recovery blocked: access-port mode is unconfirmed")
    protected = get_protected_interfaces(options)
    if protected is None:
        raise HomeAssistantError("Recovery blocked: interface protection could not be confirmed")
    if assess_port_protection(data, if_index, protected_interface_names=protected,
                              expected_interface_name=expected_name).blocked:
        raise HomeAssistantError("Recovery blocked: protected or unsafe interface")
    protected_vlans = configured_protected_vlans(options)
    if protected_vlans is None or destination_vlan in protected_vlans or source_vlan in protected_vlans:
        raise HomeAssistantError("Recovery blocked: VLAN protection policy")
    operational = await coordinator.client.walk(STATE + ".1")
    if int(operational.get(f"{STATE}.1.{destination_vlan}", -1)) != 1:
        raise HomeAssistantError("Recovery blocked: destination VLAN not live and operational")
    oid = f"{CISCO_VM_VLAN}.{if_index}"
    actual = int(await coordinator.client.get(oid))
    if actual != source_vlan:
        raise HomeAssistantError(f"Recovery blocked: live VLAN is {actual}, expected {source_vlan}")
    await coordinator.client.set_integer(oid, destination_vlan)
    verified = int(await coordinator.client.get(oid))
    if verified != destination_vlan:
        raise HomeAssistantError(f"Recovery write unverified: VLAN {verified}, expected {destination_vlan}; inspect switch before retry")
    return {"status":"verified","port":expected_name,"old_vlan":source_vlan,
            "new_vlan":destination_vlan,"readback_vlan":verified}
