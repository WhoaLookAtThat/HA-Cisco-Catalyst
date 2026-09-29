"""Tests for verified interface-description writes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.cisco_catalyst.const import IF_ALIAS
from custom_components.cisco_catalyst.coordinator import InterfaceData
from custom_components.cisco_catalyst.text import CatalystPortDescription


class PrettyValue:
    """Minimal PySNMP-like string value."""

    def __init__(self, value: str) -> None:
        self.value = value

    def prettyPrint(self) -> str:
        return self.value


@pytest.mark.asyncio
async def test_description_write_uses_exact_readback_and_convergence() -> None:
    writes: list[tuple[str, str]] = []
    reads = 0
    coordinator: Any

    async def set_string(oid: str, value: str) -> None:
        writes.append((oid, value))

    async def get(oid: str) -> PrettyValue:
        nonlocal reads
        reads += 1
        return PrettyValue("new description")

    async def refresh() -> None:
        coordinator.data.interfaces[8].description = "new description"

    coordinator = SimpleNamespace(
        client=SimpleNamespace(
            host="192.0.2.1",
            set_string=set_string,
            get=get,
        ),
        data=SimpleNamespace(
            interfaces={
                8: InterfaceData(
                    if_index=8,
                    name="GigabitEthernet1/0/1",
                    description="old description",
                )
            }
        ),
        async_request_refresh=refresh,
        write_lock=asyncio.Lock(),
        io_lock=asyncio.Lock(),
        pending_writes={},
        async_update_listeners=lambda: None,
        last_update_success=True,
        write_enabled=True,
    )

    entity = CatalystPortDescription(coordinator, 8)
    await entity.async_set_value("new description")

    assert writes == [(f"{IF_ALIAS}.8", "new description")]
    assert reads == 1
    assert coordinator.data.interfaces[8].description == "new description"
    assert coordinator.pending_writes == {}


def test_description_entity_prefers_pending_value() -> None:
    coordinator: Any = SimpleNamespace(
        client=SimpleNamespace(host="192.0.2.1"),
        data=SimpleNamespace(
            interfaces={
                8: InterfaceData(
                    if_index=8,
                    name="GigabitEthernet1/0/1",
                    description="old description",
                )
            }
        ),
        pending_writes={f"{IF_ALIAS}.8": "requested description"},
        last_update_success=True,
    )

    entity = CatalystPortDescription(coordinator, 8)
    assert entity.native_value == "requested description"
