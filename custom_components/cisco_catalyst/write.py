"""Shared serialized SNMP write/readback/reconciliation helpers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from homeassistant.exceptions import HomeAssistantError

from .coordinator import CatalystCoordinator

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

WRITE_READBACK_ATTEMPTS = 4
WRITE_READBACK_DELAY = 0.75
RECONCILE_ATTEMPTS = 2
RECONCILE_DELAY = 1.0


async def async_write_with_readback(
    coordinator: CatalystCoordinator,
    oid: str,
    value: T,
    *,
    writer: Callable[[str, T], Awaitable[None]],
    normalize_readback: Callable[[Any], T],
    expected_state: Callable[[], bool] | None = None,
    apply_verified_state: Callable[[], None] | None = None,
) -> None:
    """Serialize a write, exact-OID verification, and state reconciliation."""
    if not coordinator.write_enabled:
        raise HomeAssistantError(
            "Cisco Catalyst credentials are configured as read-only; "
            "change Credential access to Read/write in Reconfigure before using controls"
        )

    async with coordinator.write_lock:
        # Publish the requested value immediately so HA cannot render a stale
        # coordinator snapshot while Cisco converges after the SET.
        coordinator.pending_writes[oid] = value
        coordinator.async_update_listeners()
        try:
            async with coordinator.io_lock:
                await writer(oid, value)
                for attempt in range(WRITE_READBACK_ATTEMPTS):
                    if attempt:
                        await asyncio.sleep(WRITE_READBACK_DELAY)
                    if normalize_readback(await coordinator.client.get(oid)) == value:
                        break
                else:
                    raise RuntimeError(f"SNMP write verification failed for {oid}")

            # The exact-OID readback above is authoritative for the requested
            # scalar. Publish that verified value immediately so a stale Cisco bulk
            # table cannot bounce the entity back or turn a successful SET into a
            # false user-visible failure.
            if apply_verified_state is not None:
                apply_verified_state()
                coordinator.async_update_listeners()

            # Best-effort full-snapshot reconciliation still follows so related
            # telemetry can catch up. Some Catalyst agents keep bulk-walk tables
            # stale substantially longer than scalar GETs; if that happens, retain
            # the exact-OID verified state and let normal polling reconcile later.
            for attempt in range(RECONCILE_ATTEMPTS):
                if attempt:
                    await asyncio.sleep(RECONCILE_DELAY)
                await coordinator.async_request_refresh()
                if expected_state is None or expected_state():
                    break
                if apply_verified_state is not None:
                    apply_verified_state()
                    coordinator.async_update_listeners()
            else:
                _LOGGER.debug(
                    "SNMP bulk snapshot did not converge for %s after exact-OID "
                    "verification; retaining verified state until a later poll",
                    oid,
                )
        finally:
            coordinator.pending_writes.pop(oid, None)
            coordinator.async_update_listeners()
