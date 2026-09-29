"""Tests for SNMP notification receiver setup and callback behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.cisco_catalyst.const import SNMP_ENGINE_ID
from custom_components.cisco_catalyst.trap import (
    EVENT_SNMP_NOTIFICATION,
    CatalystTrapReceiver,
)


class Pretty:
    def __init__(self, value: str) -> None:
        self.value = value

    def prettyPrint(self) -> str:
        return self.value


@pytest.mark.asyncio
async def test_v3_receiver_localizes_user_to_remote_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_engine_id = Pretty("0x80000000010203")
    engine = SimpleNamespace(snmpEngineID=local_engine_id)
    remote_engine_id = object()
    requested_oids: list[str] = []
    added_users: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    transports: list[tuple[Any, Any, Any]] = []

    async def get(oid: str) -> object:
        requested_oids.append(oid)
        return remote_engine_id

    async def add_executor_job(func):
        return engine

    class FakeUdpTransport:
        def open_server_mode(self, address):
            return ("transport", address)

    class FakeReceiver:
        def __init__(self, snmp_engine, callback):
            self.snmp_engine = snmp_engine
            self.callback = callback

        def close(self, snmp_engine):
            assert snmp_engine is self.snmp_engine

    def add_v3_user(*args, **kwargs) -> None:
        added_users.append((args, kwargs))

    def add_transport(snmp_engine, domain, transport) -> None:
        transports.append((snmp_engine, domain, transport))

    monkeypatch.setattr(
        "custom_components.cisco_catalyst.trap.build_warmed_engine",
        lambda: engine,
    )
    monkeypatch.setattr(
        "custom_components.cisco_catalyst.trap.config.add_v3_user",
        add_v3_user,
    )
    monkeypatch.setattr(
        "custom_components.cisco_catalyst.trap.config.add_transport",
        add_transport,
    )
    monkeypatch.setattr(
        "custom_components.cisco_catalyst.trap._DiagnosticUdpTransport",
        FakeUdpTransport,
    )
    monkeypatch.setattr(
        "custom_components.cisco_catalyst.trap.ntfrcv.NotificationReceiver",
        FakeReceiver,
    )

    client = SimpleNamespace(
        version="3",
        username="ha-user",
        auth_key="auth-key",
        priv_key="priv-key",
        auth_protocol="sha",
        priv_protocol="aes128",
        get=get,
    )
    coordinator = SimpleNamespace(client=client)
    hass = SimpleNamespace(async_add_executor_job=add_executor_job)

    receiver = CatalystTrapReceiver(coordinator, 1162)
    await receiver.async_start(hass)

    assert requested_oids == [SNMP_ENGINE_ID]
    assert len(added_users) == 2
    local_args, local_kwargs = added_users[0]
    assert local_args[0] is engine
    assert local_args[1] == "ha-user"
    assert "securityEngineId" not in local_kwargs
    remote_args, remote_kwargs = added_users[1]
    assert remote_args[0] is engine
    assert remote_args[1] == "ha-user"
    assert remote_kwargs["securityEngineId"] is remote_engine_id
    assert len(transports) == 1
    assert transports[0][0] is engine
    assert transports[0][2] == ("transport", ("0.0.0.0", 1162))


def test_notification_fires_event_and_requests_refresh() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    tasks: list[Any] = []
    refresh_calls = 0

    async def refresh() -> None:
        nonlocal refresh_calls
        refresh_calls += 1

    hass = SimpleNamespace(
        bus=SimpleNamespace(async_fire=lambda event, payload: events.append((event, payload))),
        async_create_task=lambda coro: tasks.append(coro),
    )
    coordinator = SimpleNamespace(
        client=SimpleNamespace(host="192.0.2.10"),
        hass=hass,
        async_request_refresh=refresh,
    )
    receiver = CatalystTrapReceiver(coordinator, 1162)
    receiver._engine = SimpleNamespace(snmpEngineID=Pretty("0x80000000010203"))

    receiver._notification(
        receiver._engine,
        object(),
        Pretty("engine"),
        Pretty(""),
        [(Pretty("1.2.3"), Pretty("value"))],
        None,
    )

    assert events == [
        (
            EVENT_SNMP_NOTIFICATION,
            {
                "host": "192.0.2.10",
                "receiver_engine_id": "0x80000000010203",
                "context_engine_id": "engine",
                "context_name": "",
                "var_binds": {"1.2.3": "value"},
            },
        )
    ]
    assert len(tasks) == 1

    tasks[0].close()
    assert refresh_calls == 0


def test_close_unregisters_receiver_before_dispatcher() -> None:
    """Receiver cleanup follows the PySNMP 7.1 NotificationReceiver API."""
    calls: list[tuple[str, Any]] = []
    engine = SimpleNamespace(close_dispatcher=lambda: calls.append(("dispatcher", None)))
    notification_receiver = SimpleNamespace(
        close=lambda snmp_engine: calls.append(("receiver", snmp_engine))
    )
    receiver = CatalystTrapReceiver(SimpleNamespace(), 1162)
    receiver._engine = engine
    receiver._receiver = notification_receiver

    receiver.close()

    assert calls == [("receiver", engine), ("dispatcher", None)]
    assert receiver._receiver is None
    assert receiver._engine is None
