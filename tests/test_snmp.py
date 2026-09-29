"""Tests for the asynchronous SNMP client."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.cisco_catalyst import snmp


class FakeEngine:
    def close_dispatcher(self) -> None:
        pass


class PrettyValue:
    def __init__(self, value: str) -> None:
        self.value = value

    def prettyPrint(self) -> str:
        return self.value


class FakeOid(PrettyValue):
    pass


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> snmp.CatalystSnmpClient:
    monkeypatch.setattr(snmp, "SnmpEngine", FakeEngine)
    client = snmp.CatalystSnmpClient("192.0.2.1", 161, "public", "private")
    client._engine = FakeEngine()
    return client


@pytest.mark.asyncio
async def test_get_returns_value(client, monkeypatch) -> None:
    expected = PrettyValue("switch")
    async def fake_target(): return object()
    async def fake_get_cmd(*args: Any, **kwargs: Any):
        return None, 0, 0, [(FakeOid("1.3.6.1.2.1.1.5.0"), expected)]
    monkeypatch.setattr(client, "_target", fake_target)
    monkeypatch.setattr(snmp, "get_cmd", fake_get_cmd)
    assert await client.get("1.3.6.1.2.1.1.5.0") is expected


@pytest.mark.asyncio
async def test_get_raises_on_transport_error(client, monkeypatch) -> None:
    async def fake_target(): return object()
    async def fake_get_cmd(*args: Any, **kwargs: Any):
        return "timeout", 0, 0, []
    monkeypatch.setattr(client, "_target", fake_target)
    monkeypatch.setattr(snmp, "get_cmd", fake_get_cmd)
    with pytest.raises(snmp.CatalystSnmpError, match="timeout"):
        await client.get("1.3.6.1.2.1.1.5.0")


@pytest.mark.asyncio
async def test_walk_collects_rows(client, monkeypatch) -> None:
    async def fake_target(): return object()
    async def fake_walk(*args: Any, **kwargs: Any):
        yield None, 0, 0, [(FakeOid("1.2.3.1"), PrettyValue("one"))]
        yield None, 0, 0, [(FakeOid("1.2.3.2"), PrettyValue("two"))]
    monkeypatch.setattr(client, "_target", fake_target)
    monkeypatch.setattr(snmp, "bulk_walk_cmd", fake_walk)
    result = await client.walk("1.2.3")
    assert set(result) == {"1.2.3.1", "1.2.3.2"}


@pytest.mark.asyncio
async def test_set_integer_uses_write_community(client, monkeypatch) -> None:
    calls: list[tuple[Any, ...]] = []
    async def fake_target(): return object()
    async def fake_set_cmd(*args: Any, **kwargs: Any):
        calls.append(args)
        return None, 0, 0, []
    monkeypatch.setattr(client, "_target", fake_target)
    monkeypatch.setattr(snmp, "set_cmd", fake_set_cmd)
    await client.set_integer("1.2.3.4", 1)
    assert calls[0][1].communityName == "private"


def test_v3_uses_usm_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snmp, "SnmpEngine", FakeEngine)
    client = snmp.CatalystSnmpClient(
        "192.0.2.1", 161, version="3", username="ha",
        auth_key="authentication", priv_key="privacy",
    )
    client._engine = FakeEngine()
    auth = client._auth()
    assert auth.userName == "ha"
    assert auth.authKey is not None
    assert auth.privKey is not None


def test_check_raises_on_pdu_error() -> None:
    status = SimpleNamespace(prettyPrint=lambda: "notWritable")
    with pytest.raises(snmp.CatalystSnmpError, match="notWritable"):
        snmp.CatalystSnmpClient._check(None, status)


@pytest.mark.asyncio
async def test_async_initialize_builds_engine_in_executor(monkeypatch) -> None:
    built = FakeEngine()
    monkeypatch.setattr(snmp, "build_warmed_engine", lambda: built)
    hass = SimpleNamespace(async_add_executor_job=AsyncMock(return_value=built))
    test_client = snmp.CatalystSnmpClient("192.0.2.1", 161, "public", "private")
    await test_client.async_initialize(hass)
    await test_client.async_initialize(hass)
    hass.async_add_executor_job.assert_awaited_once()
    assert test_client._engine is built


def test_uninitialized_client_requires_engine() -> None:
    test_client = snmp.CatalystSnmpClient("192.0.2.1", 161, "public", "private")
    with pytest.raises(snmp.CatalystSnmpError, match="not been initialized"):
        test_client._require_engine()


def test_close_resets_engine(client) -> None:
    client.close()
    assert client._engine is None
