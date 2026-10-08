"""Tests for Cisco Catalyst config-entry lifecycle."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.cisco_catalyst import async_unload_entry


@pytest.mark.asyncio
async def test_unload_entry_closes_runtime_resources() -> None:
    """Successful platform unload closes integration-owned resources."""
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_unload_platforms=AsyncMock(return_value=True))
    )
    client = Mock()
    trap_receiver = Mock()
    entry = SimpleNamespace(
        entry_id="test-entry",
        runtime_data=SimpleNamespace(client=client, trap_receiver=trap_receiver),
    )

    assert await async_unload_entry(hass, entry) is True
    trap_receiver.close.assert_called_once_with()
    client.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_unload_entry_preserves_runtime_on_platform_failure() -> None:
    """Failed platform unload leaves integration-owned resources available."""
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_unload_platforms=AsyncMock(return_value=False))
    )
    client = Mock()
    trap_receiver = Mock()
    entry = SimpleNamespace(
        entry_id="test-entry",
        runtime_data=SimpleNamespace(client=client, trap_receiver=trap_receiver),
    )

    assert await async_unload_entry(hass, entry) is False
    trap_receiver.close.assert_not_called()
    client.close.assert_not_called()
