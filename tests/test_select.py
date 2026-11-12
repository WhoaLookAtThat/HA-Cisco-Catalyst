"""Tests for safe access-VLAN selection."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.cisco_catalyst.const import CISCO_VM_VLAN
from custom_components.cisco_catalyst.select import (
    CatalystAccessVlanSelect,
    _selectable_vlans,
    async_setup_entry,
)


def _coordinator(
    *,
    access_vlan: int | None = 1,
    access_vlan_type: int | None = 1,
    is_trunk: bool | None = False,
):
    interface = SimpleNamespace(
        if_index=44,
        name="GigabitEthernet1/0/37",
        description="",
        access_vlan=access_vlan,
        access_vlan_type=access_vlan_type,
        is_trunk=is_trunk,
    )
    client = SimpleNamespace(
        host="192.0.2.10",
        set_integer=AsyncMock(),
        get=AsyncMock(return_value=1),
    )
    return SimpleNamespace(
        client=client,
        data=SimpleNamespace(
            interfaces={44: interface},
            operational_vlans={1, 20, 1002, 4094},
        ),
        write_enabled=True,
        write_lock=asyncio.Lock(),
        io_lock=asyncio.Lock(),
        pending_writes={},
        async_update_listeners=lambda: None,
        async_request_refresh=AsyncMock(),
        last_update_success=True,
    )


def test_selectable_vlans_uses_existing_operational_vlan_inventory() -> None:
    coordinator = _coordinator()
    assert _selectable_vlans(coordinator) == [1, 20, 4094]


def test_access_vlan_select_exposes_existing_vlan_choices() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(coordinator, 44, {"protected_interfaces": ""})

    assert entity.current_option == "1"
    assert entity.options == ["1", "20", "4094"]
    assert entity.available is True
    assert entity.extra_state_attributes["credential_access"] == "read_write"

    coordinator.pending_writes[f"{CISCO_VM_VLAN}.44"] = 20
    assert entity.current_option == "20"


@pytest.mark.asyncio
async def test_access_vlan_noop_select_uses_exact_oid_readback() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(coordinator, 44, {"protected_interfaces": ""})

    await entity.async_select_option("1")

    coordinator.client.set_integer.assert_awaited_once_with(
        f"{CISCO_VM_VLAN}.44", 1
    )
    coordinator.client.get.assert_any_await(f"{CISCO_VM_VLAN}.44")
    assert coordinator.data.interfaces[44].access_vlan == 1


@pytest.mark.asyncio
async def test_access_vlan_rejects_nonexistent_or_reserved_choices() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(coordinator, 44)

    for value in ("2", "1002", "1.0", "bogus"):
        with pytest.raises(HomeAssistantError):
            await entity.async_select_option(value)

    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_rejects_trunk_unknown_or_nonstatic() -> None:
    for kwargs in (
        {"is_trunk": True},
        {"is_trunk": None},
        {"access_vlan_type": 2},
    ):
        coordinator = _coordinator(**kwargs)
        entity = CatalystAccessVlanSelect(coordinator, 44)
        assert entity.available is False

        with pytest.raises(HomeAssistantError):
            await entity.async_select_option("1")


@pytest.mark.asyncio
async def test_select_platform_adds_nothing_for_read_only_entry() -> None:
    coordinator = _coordinator()
    coordinator.write_enabled = False
    entry = SimpleNamespace(runtime_data=coordinator)
    added: list[object] = []

    def add_entities(entities):
        added.extend(list(entities))

    await async_setup_entry(None, entry, add_entities)
    assert added == []


@pytest.mark.asyncio
async def test_access_vlan_blocks_when_protection_policy_absent() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(coordinator, 44)
    with pytest.raises(HomeAssistantError, match="protection"):
        await entity.async_select_option("20")
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_blocks_explicitly_protected_port() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(
        coordinator, 44, {"protected_interfaces": "GigabitEthernet1/0/37"}
    )
    with pytest.raises(HomeAssistantError, match="protected_interface"):
        await entity.async_select_option("20")
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_blocks_port_identity_remapping() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(
        coordinator, 44, {"protected_interfaces": ""}
    )
    coordinator.data.interfaces[44].name = "GigabitEthernet1/0/38"
    with pytest.raises(HomeAssistantError, match="interface_identity_changed"):
        await entity.async_select_option("20")
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_blocks_invalid_stored_protection_policy() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(
        coordinator, 44, {"protected_interfaces": "Gi1/0/37"}
    )
    with pytest.raises(HomeAssistantError, match="Invalid protected-port"):
        await entity.async_select_option("20")
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_rejects_protected_destination_even_direct_service_value() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(
        coordinator, 44, {"protected_interfaces": "", "protected_vlans": "20"}
    )
    assert "20" in entity.options  # UI filtering alone is never the enforcement boundary.
    with pytest.raises(HomeAssistantError, match="Destination VLAN 20 is protected"):
        await entity.async_select_option("20")
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_rejects_moving_away_from_protected_source() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(
        coordinator, 44, {"protected_interfaces": "", "protected_vlans": "1"}
    )
    with pytest.raises(HomeAssistantError, match="Current VLAN 1 is protected"):
        await entity.async_select_option("20")
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_rejects_malformed_protected_vlan_policy() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(
        coordinator, 44, {"protected_interfaces": "", "protected_vlans": "20,20"}
    )
    with pytest.raises(HomeAssistantError, match="Invalid protected-VLAN"):
        await entity.async_select_option("1")
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_allows_unprotected_destination_with_empty_vlan_policy() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(
        coordinator, 44, {"protected_interfaces": "", "protected_vlans": ""}
    )
    await entity.async_select_option("1")
    coordinator.client.set_integer.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_vlan_absent_optional_vlan_policy_preserves_existing_behavior() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(coordinator, 44, {"protected_interfaces": ""})
    await entity.async_select_option("1")
    coordinator.client.set_integer.assert_awaited_once()


@pytest.mark.asyncio
async def test_inactive_static_port_registered_then_available_after_poll_without_reload() -> None:
    """A VLAN 999 recovery must not require re-running platform setup."""
    coordinator = _coordinator(access_vlan=999)
    added = []
    entry = SimpleNamespace(runtime_data=coordinator, options={"protected_interfaces": "", "protected_vlans": ""})

    def add_entities(entities):
        added.extend(list(entities))

    await async_setup_entry(None, entry, add_entities)
    assert len(added) == 1
    entity = added[0]
    assert entity.current_option == "999"
    assert entity.available is False
    assert "999" not in entity.options

    # Simulate authoritative switch polling after successful recovery.
    # No new entity, HA reload, or SNMP write is involved.
    coordinator.data.interfaces[44].access_vlan = 996
    coordinator.data.operational_vlans.add(996)
    assert len(added) == 1
    assert added[0] is entity
    assert entity.available is True
    assert entity.current_option == "996"
    assert "996" in entity.options
    assert "1" in entity.options
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_switch_changes_and_inactivation_update_existing_selector() -> None:
    """Existing entity always reflects new coordinator polling snapshots."""
    coordinator = _coordinator(access_vlan=996)
    coordinator.data.operational_vlans.add(996)
    added = []
    await async_setup_entry(
        None, SimpleNamespace(runtime_data=coordinator, options={}),
        lambda entities: added.extend(list(entities)),
    )
    assert len(added) == 1
    entity = added[0]
    assert entity.available is True
    assert entity.current_option == "996"

    coordinator.data.interfaces[44].access_vlan = 1
    assert entity.current_option == "1"
    assert entity.available is True

    coordinator.data.interfaces[44].access_vlan = 999
    assert entity.current_option == "999"
    assert entity.available is False
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_nonstatic_and_trunk_ports_do_not_register_vlan_selectors() -> None:
    for kwargs in ({"access_vlan_type": None}, {"access_vlan_type": 2},
                   {"is_trunk": True}, {"is_trunk": None},
                   {"access_vlan": None}):
        coordinator = _coordinator(**kwargs)
        added = []
        await async_setup_entry(
            None, SimpleNamespace(runtime_data=coordinator, options={}),
            lambda entities: added.extend(list(entities)),
        )
        assert added == [], kwargs


@pytest.mark.asyncio
async def test_recovered_port_can_move_to_vlan_one_without_reload() -> None:
    """Regression: orphan recovery to 996 followed by ordinary 996 -> 1 write."""
    coordinator = _coordinator(access_vlan=999)
    coordinator.data.operational_vlans.add(996)
    added = []
    await async_setup_entry(
        None,
        SimpleNamespace(runtime_data=coordinator, options={
            "protected_interfaces": "", "protected_vlans": "",
        }),
        lambda entities: added.extend(list(entities)),
    )
    assert len(added) == 1
    entity = added[0]
    # The setup test uses SimpleNamespace instead of a real HA ConfigEntry.
    # Supply its .options mapping explicitly to model ConfigEntry.options;
    # production setup uses a real ConfigEntry and needs no such adjustment.
    entity._options_source = {"protected_interfaces": "", "protected_vlans": ""}
    assert entity.available is False

    # Switch-side recovery is already completed and observed via poll.
    coordinator.data.interfaces[44].access_vlan = 996
    assert entity.available is True
    assert entity.current_option == "996"

    # Live pre-SET check confirms source 996; readback verifies destination 1.
    coordinator.client.get.side_effect = [996, 1]
    await entity.async_select_option("1")

    coordinator.client.set_integer.assert_awaited_once_with(
        f"{CISCO_VM_VLAN}.44", 1
    )
    assert coordinator.client.get.await_count == 2
    assert entity.current_option == "1"
    assert entity.available is True
    assert coordinator.async_request_refresh.await_count >= 1
    assert len(added) == 1


@pytest.mark.asyncio
async def test_fresh_coordinator_snapshot_updates_existing_recovered_select_without_reload() -> None:
    """Polling replaces coordinator.data: the select must not capture the old port."""
    coordinator = _coordinator(access_vlan=999)
    registered = []
    await async_setup_entry(
        None, SimpleNamespace(runtime_data=coordinator, options={}),
        lambda entities: registered.extend(list(entities)),
    )
    assert len(registered) == 1
    entity = registered[0]
    original_snapshot = coordinator.data
    assert not entity.available

    # Real DataUpdateCoordinator polling publishes a new snapshot object.
    fresh = _coordinator(access_vlan=996).data
    fresh.operational_vlans.add(996)
    coordinator.data = fresh
    assert coordinator.data is not original_snapshot
    assert entity.available is True
    assert entity.current_option == "996"
    assert "1" in entity.options

    # An externally deleted VLAN must disable writes on the same entity.
    coordinator.data.operational_vlans.remove(996)
    assert entity.available is False
    assert entity.current_option == "996"
    coordinator.client.set_integer.assert_not_awaited()
