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
    entity = CatalystAccessVlanSelect(coordinator, 44)

    assert entity.current_option == "1"
    assert entity.options == ["1", "20", "4094"]
    assert entity.available is True
    assert entity.extra_state_attributes["credential_access"] == "read_write"

    coordinator.pending_writes[f"{CISCO_VM_VLAN}.44"] = 20
    assert entity.current_option == "20"


@pytest.mark.asyncio
async def test_access_vlan_noop_select_uses_exact_oid_readback() -> None:
    coordinator = _coordinator()
    entity = CatalystAccessVlanSelect(coordinator, 44)

    await entity.async_select_option("1")

    coordinator.client.set_integer.assert_awaited_once_with(
        f"{CISCO_VM_VLAN}.44", 1
    )
    coordinator.client.get.assert_awaited_once_with(f"{CISCO_VM_VLAN}.44")
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
