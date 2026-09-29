"""Tests for declared Cisco Catalyst write access."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.cisco_catalyst.write import async_write_with_readback


@pytest.mark.asyncio
async def test_declared_read_only_blocks_set_before_snmp_write() -> None:
    writer = AsyncMock()
    coordinator = SimpleNamespace(write_enabled=False)

    with pytest.raises(HomeAssistantError, match="configured as read-only"):
        await async_write_with_readback(
            coordinator,
            "1.2.3.4",
            1,
            writer=writer,
            normalize_readback=int,
        )

    writer.assert_not_awaited()
