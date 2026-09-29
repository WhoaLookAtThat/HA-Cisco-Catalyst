"""Tests for shared SNMP write/readback behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.cisco_catalyst import write


@pytest.mark.asyncio
async def test_write_readback_retries_exact_oid(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[tuple[str, int]] = []
    reads = 0
    refreshes = 0

    async def set_integer(oid: str, value: int) -> None:
        writes.append((oid, value))

    async def get(oid: str) -> int:
        nonlocal reads
        reads += 1
        return 1 if reads == 1 else 2

    async def refresh() -> None:
        nonlocal refreshes
        refreshes += 1

    async def no_sleep(delay: float) -> None:
        return None

    coordinator: Any = SimpleNamespace(
        client=SimpleNamespace(get=get),
        async_request_refresh=refresh,
        write_lock=asyncio.Lock(),
        io_lock=asyncio.Lock(),
        pending_writes={},
        async_update_listeners=lambda: None,
        write_enabled=True,
    )
    monkeypatch.setattr(write.asyncio, "sleep", no_sleep)

    await write.async_write_with_readback(
        coordinator,
        "1.2.3.4",
        2,
        writer=set_integer,
        normalize_readback=int,
    )

    assert writes == [("1.2.3.4", 2)]
    assert reads == 2
    assert refreshes == 1


@pytest.mark.asyncio
async def test_write_readback_stops_on_first_matching_get() -> None:
    writes = 0
    reads = 0
    refreshes = 0

    async def set_integer(oid: str, value: int) -> None:
        nonlocal writes
        writes += 1

    async def get(oid: str) -> int:
        nonlocal reads
        reads += 1
        return 2

    async def refresh() -> None:
        nonlocal refreshes
        refreshes += 1

    coordinator: Any = SimpleNamespace(
        client=SimpleNamespace(get=get),
        async_request_refresh=refresh,
        write_lock=asyncio.Lock(),
        io_lock=asyncio.Lock(),
        pending_writes={},
        async_update_listeners=lambda: None,
        write_enabled=True,
    )

    await write.async_write_with_readback(
        coordinator,
        "1.2.3.4",
        2,
        writer=set_integer,
        normalize_readback=int,
    )

    assert writes == 1
    assert reads == 1
    assert refreshes == 1


@pytest.mark.asyncio
async def test_write_readback_fails_without_full_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = 0
    reads = 0
    refreshes = 0

    async def set_integer(oid: str, value: int) -> None:
        nonlocal writes
        writes += 1

    async def get(oid: str) -> int:
        nonlocal reads
        reads += 1
        return 1

    async def refresh() -> None:
        nonlocal refreshes
        refreshes += 1

    async def no_sleep(delay: float) -> None:
        return None

    coordinator: Any = SimpleNamespace(
        client=SimpleNamespace(get=get),
        async_request_refresh=refresh,
        write_lock=asyncio.Lock(),
        io_lock=asyncio.Lock(),
        pending_writes={},
        async_update_listeners=lambda: None,
        write_enabled=True,
    )
    monkeypatch.setattr(write.asyncio, "sleep", no_sleep)

    with pytest.raises(RuntimeError, match="SNMP write verification failed"):
        await write.async_write_with_readback(
            coordinator,
            "1.2.3.4",
            2,
            writer=set_integer,
            normalize_readback=int,
        )

    assert writes == 1
    assert reads == write.WRITE_READBACK_ATTEMPTS
    assert refreshes == 0


@pytest.mark.asyncio
async def test_write_preserves_verified_state_when_bulk_snapshot_stays_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refreshes = 0
    state = {"value": 1}

    async def set_integer(oid: str, value: int) -> None:
        pass

    async def get(oid: str) -> int:
        return 2

    async def refresh() -> None:
        nonlocal refreshes
        refreshes += 1
        state["value"] = 1

    async def no_sleep(delay: float) -> None:
        pass

    coordinator: Any = SimpleNamespace(
        client=SimpleNamespace(get=get),
        async_request_refresh=refresh,
        write_lock=asyncio.Lock(),
        io_lock=asyncio.Lock(),
        pending_writes={},
        async_update_listeners=lambda: None,
        write_enabled=True,
    )
    monkeypatch.setattr(write.asyncio, "sleep", no_sleep)

    await write.async_write_with_readback(
        coordinator,
        "1.2.3.4",
        2,
        writer=set_integer,
        normalize_readback=int,
        expected_state=lambda: state["value"] == 2,
        apply_verified_state=lambda: state.__setitem__("value", 2),
    )

    assert refreshes == write.RECONCILE_ATTEMPTS
    assert state["value"] == 2
    assert coordinator.pending_writes == {}


@pytest.mark.asyncio
async def test_write_reconciliation_stops_when_bulk_snapshot_matches() -> None:
    refreshes = 0
    state = {"value": 1}

    async def set_integer(oid: str, value: int) -> None:
        pass

    async def get(oid: str) -> int:
        return 2

    async def refresh() -> None:
        nonlocal refreshes
        refreshes += 1
        state["value"] = 2

    coordinator: Any = SimpleNamespace(
        client=SimpleNamespace(get=get),
        async_request_refresh=refresh,
        write_lock=asyncio.Lock(),
        io_lock=asyncio.Lock(),
        pending_writes={},
        async_update_listeners=lambda: None,
        write_enabled=True,
    )

    await write.async_write_with_readback(
        coordinator,
        "1.2.3.4",
        2,
        writer=set_integer,
        normalize_readback=int,
        expected_state=lambda: state["value"] == 2,
        apply_verified_state=lambda: state.__setitem__("value", 2),
    )

    assert refreshes == 1
    assert state["value"] == 2
    assert coordinator.pending_writes == {}
