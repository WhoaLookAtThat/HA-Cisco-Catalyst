"""Tests for safe access-VLAN configuration controls."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.cisco_catalyst.const import CISCO_VM_VLAN
from custom_components.cisco_catalyst.number import CatalystAccessVlanNumber


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
            operational_vlans={1, 20},
        ),
        write_enabled=True,
        write_lock=asyncio.Lock(),
        io_lock=asyncio.Lock(),
        pending_writes={},
        async_update_listeners=lambda: None,
        async_request_refresh=AsyncMock(),
        last_update_success=True,
    )


def test_access_vlan_entity_reads_authoritative_and_pending_values() -> None:
    coordinator = _coordinator(access_vlan=1)
    entity = CatalystAccessVlanNumber(coordinator, 44)

    assert entity.native_value == 1
    assert entity.available is True
    assert entity.extra_state_attributes["credential_access"] == "read_write"
    assert entity.extra_state_attributes["cisco_catalyst_role"] == "access_vlan"

    coordinator.pending_writes[f"{CISCO_VM_VLAN}.44"] = 20
    assert entity.native_value == 20


@pytest.mark.asyncio
async def test_access_vlan_noop_set_uses_exact_oid_readback() -> None:
    coordinator = _coordinator(access_vlan=1)
    entity = CatalystAccessVlanNumber(coordinator, 44)

    await entity.async_set_native_value(1)

    coordinator.client.set_integer.assert_awaited_once_with(
        f"{CISCO_VM_VLAN}.44", 1
    )
    coordinator.client.get.assert_awaited_once_with(f"{CISCO_VM_VLAN}.44")
    assert coordinator.data.interfaces[44].access_vlan == 1
    assert coordinator.pending_writes == {}


@pytest.mark.asyncio
async def test_access_vlan_rejects_non_integer_and_out_of_range() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanNumber(coordinator, 44)

    with pytest.raises(HomeAssistantError, match="whole-number"):
        await entity.async_set_native_value(1.5)
    with pytest.raises(HomeAssistantError, match="between 1 and 4094"):
        await entity.async_set_native_value(4095)
    with pytest.raises(HomeAssistantError, match="reserved"):
        await entity.async_set_native_value(1002)
    with pytest.raises(HomeAssistantError, match="already exist and be operational"):
        await entity.async_set_native_value(30)

    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_rejects_trunk_or_unknown_mode() -> None:
    for trunk_state in (True, None):
        coordinator = _coordinator(is_trunk=trunk_state)
        entity = CatalystAccessVlanNumber(coordinator, 44)
        assert entity.available is False

        with pytest.raises(HomeAssistantError, match="confirmed non-trunk"):
            await entity.async_set_native_value(1)
        coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_rejects_missing_authoritative_vlan() -> None:
    coordinator = _coordinator(access_vlan=None)
    entity = CatalystAccessVlanNumber(coordinator, 44)
    assert entity.available is False

    with pytest.raises(HomeAssistantError, match="unavailable"):
        await entity.async_set_native_value(1)
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_vlan_rejects_non_static_vlan_type() -> None:
    coordinator = _coordinator(access_vlan_type=2)
    entity = CatalystAccessVlanNumber(coordinator, 44)
    assert entity.available is False

    with pytest.raises(HomeAssistantError, match="vmVlanType static"):
        await entity.async_set_native_value(1)
    coordinator.client.set_integer.assert_not_awaited()


@pytest.mark.asyncio
async def test_number_platform_adds_nothing_for_read_only_entry() -> None:
    from custom_components.cisco_catalyst.number import async_setup_entry

    coordinator = _coordinator()
    coordinator.write_enabled = False
    entry = SimpleNamespace(runtime_data=coordinator)
    added: list[object] = []

    def add_entities(entities):
        added.extend(list(entities))

    await async_setup_entry(None, entry, add_entities)
    assert added == []


def test_access_vlan_unavailable_when_current_vlan_inventory_is_missing() -> None:
    coordinator = _coordinator(access_vlan=1)
    coordinator.data.operational_vlans = set()
    entity = CatalystAccessVlanNumber(coordinator, 44)
    assert entity.available is False
