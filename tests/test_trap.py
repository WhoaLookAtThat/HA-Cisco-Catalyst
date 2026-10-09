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


def _receiver_harness() -> tuple[CatalystTrapReceiver, list[tuple[str, dict[str, Any]]], list[Any]]:
    events: list[tuple[str, dict[str, Any]]] = []
    tasks: list[Any] = []

    async def refresh() -> None:
        return None

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
    return receiver, events, tasks


def _notification_var_binds(notification_oid: str) -> list[tuple[Pretty, Pretty]]:
    return [
        (Pretty("1.3.6.1.2.1.1.3.0"), Pretty("161588994")),
        (Pretty("1.3.6.1.6.3.1.1.4.1.0"), Pretty(notification_oid)),
    ]


def _poe_var_binds(port: int, status: int) -> list[tuple[Pretty, Pretty]]:
    return [
        *_notification_var_binds("1.3.6.1.2.1.105.0.1"),
        (
            Pretty(f"1.3.6.1.2.1.105.1.1.1.6.1.{port}"),
            Pretty(str(status)),
        ),
    ]


def test_notification_fires_event_and_requests_refresh() -> None:
    receiver, events, tasks = _receiver_harness()

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
                "notification_oid": "",
                "notification_type": "unknown",
                "var_binds": {"1.2.3": "value"},
            },
        )
    ]
    assert len(tasks) == 1

    tasks[0].close()


@pytest.mark.parametrize(
    ("notification_oid", "notification_type"),
    [
        ("1.3.6.1.6.3.1.1.5.1", "cold_start"),
        ("1.3.6.1.6.3.1.1.5.2", "warm_start"),
        ("1.3.6.1.6.3.1.1.5.5", "snmp_authentication_failure"),
        ("1.3.6.1.2.1.47.2.0.1", "entity_config_change"),
        ("1.3.6.1.4.1.9.9.109.2.0.1", "cpu_threshold_rising"),
        ("1.3.6.1.4.1.9.9.109.2.0.2", "cpu_threshold_falling"),
        ("1.3.6.1.4.1.9.9.13.3.0.1", "environment_shutdown"),
        ("1.3.6.1.4.1.9.9.13.3.0.2", "environment_voltage"),
        ("1.3.6.1.4.1.9.9.13.3.0.3", "environment_temperature"),
        ("1.3.6.1.4.1.9.9.13.3.0.4", "environment_fan"),
        ("1.3.6.1.4.1.9.9.13.3.0.5", "environment_supply"),
        (
            "1.3.6.1.4.1.9.9.13.3.0.6",
            "environment_voltage_status_change",
        ),
        (
            "1.3.6.1.4.1.9.9.13.3.0.7",
            "environment_temperature_status_change",
        ),
        ("1.3.6.1.4.1.9.9.13.3.0.8", "environment_fan_status_change"),
        (
            "1.3.6.1.4.1.9.9.13.3.0.9",
            "environment_supply_status_change",
        ),
        ("1.3.6.1.4.1.9.9.548.0.2", "errdisable_interface"),
        ("1.3.6.1.4.1.9.9.548.0.1.1", "errdisable_interface_legacy"),
        ("1.3.6.1.4.1.9.9.10.1.3.0.4", "flash_device_change"),
        (
            "1.3.6.1.4.1.9.9.10.1.3.0.5",
            "flash_device_inserted_legacy",
        ),
        (
            "1.3.6.1.4.1.9.9.10.1.3.0.6",
            "flash_device_removed_legacy",
        ),
        ("1.3.6.1.4.1.9.9.10.1.3.0.7", "flash_device_inserted"),
        ("1.3.6.1.4.1.9.9.10.1.3.0.8", "flash_device_removed"),
        ("1.3.6.1.4.1.9.9.10.1.3.0.9", "flash_partition_low_space"),
        (
            "1.3.6.1.4.1.9.9.10.1.3.0.10",
            "flash_partition_low_space_recovery",
        ),
        (
            "1.3.6.1.4.1.9.9.10.1.3.0.11",
            "flash_device_change_extended",
        ),
        (
            "1.3.6.1.4.1.9.9.10.1.3.0.12",
            "flash_device_inserted_extended",
        ),
        (
            "1.3.6.1.4.1.9.9.10.1.3.0.13",
            "flash_device_removed_extended",
        ),
        (
            "1.3.6.1.4.1.9.9.706.0.1",
            "transceiver_monitor_status_change",
        ),
    ],
)
def test_health_notification_adds_stable_type(
    notification_oid: str, notification_type: str
) -> None:
    receiver, events, tasks = _receiver_harness()

    receiver._notification(
        receiver._engine,
        object(),
        Pretty("switch-engine"),
        Pretty(""),
        _notification_var_binds(notification_oid),
        None,
    )

    assert len(events) == 1
    payload = events[0][1]
    assert payload["notification_oid"] == notification_oid
    assert payload["notification_type"] == notification_type
    assert len(tasks) == 1

    tasks[0].close()


def test_poe_notification_adds_port_semantics() -> None:
    receiver, events, tasks = _receiver_harness()

    receiver._notification(
        receiver._engine,
        object(),
        Pretty("switch-engine"),
        Pretty(""),
        _poe_var_binds(38, 3),
        None,
    )

    assert len(events) == 1
    payload = events[0][1]
    assert payload["notification_oid"] == "1.3.6.1.2.1.105.0.1"
    assert payload["notification_type"] == "poe_port_status"
    assert payload["pse_group"] == 1
    assert payload["pse_port"] == 38
    assert payload["pse_detection_status"] == 3
    assert payload["pse_detection_status_name"] == "delivering_power"
    assert len(tasks) == 1

    tasks[0].close()


def test_duplicate_poe_notification_is_suppressed_but_other_port_is_not() -> None:
    receiver, events, tasks = _receiver_harness()

    for port in (38, 38, 36):
        receiver._notification(
            receiver._engine,
            object(),
            Pretty("switch-engine"),
            Pretty(""),
            _poe_var_binds(port, 3),
            None,
        )

    assert [event[1]["pse_port"] for event in events] == [38, 36]
    assert len(tasks) == 2

    for task in tasks:
        task.close()


def test_duplicate_health_notification_ignores_uptime_changes() -> None:
    receiver, events, tasks = _receiver_harness()
    auth_oid = "1.3.6.1.6.3.1.1.5.5"

    first = _notification_var_binds(auth_oid)
    second = [
        (Pretty("1.3.6.1.2.1.1.3.0"), Pretty("161589100")),
        (Pretty("1.3.6.1.6.3.1.1.4.1.0"), Pretty(auth_oid)),
    ]

    for var_binds in (first, second):
        receiver._notification(
            receiver._engine,
            object(),
            Pretty("switch-engine"),
            Pretty(""),
            var_binds,
            None,
        )

    assert len(events) == 1
    assert len(tasks) == 1
    tasks[0].close()


def test_health_notification_storm_is_bounded() -> None:
    receiver, events, tasks = _receiver_harness()
    auth_oid = "1.3.6.1.6.3.1.1.5.5"
    source_oid = "1.3.6.1.6.3.18.1.3.0"

    for index in range(12):
        receiver._notification(
            receiver._engine,
            object(),
            Pretty("switch-engine"),
            Pretty(""),
            [
                *_notification_var_binds(auth_oid),
                (Pretty(source_oid), Pretty(f"192.0.2.{index + 1}")),
            ],
            None,
        )

    assert len(events) == 10
    assert len(tasks) == 10

    for task in tasks:
        task.close()




def test_link_notification_is_a_refresh_hint_with_ifindex() -> None:
    receiver, events, tasks = _receiver_harness()
    receiver._notification(
        receiver._engine,
        object(),
        Pretty("switch-engine"),
        Pretty(""),
        [
            *_notification_var_binds("1.3.6.1.6.3.1.1.5.3"),
            (Pretty("1.3.6.1.2.1.2.2.1.1.38"), Pretty("38")),
            (Pretty("1.3.6.1.2.1.2.2.1.7.38"), Pretty("1")),
            (Pretty("1.3.6.1.2.1.2.2.1.8.38"), Pretty("2")),
        ],
        None,
    )

    assert len(events) == 1
    payload = events[0][1]
    assert payload["notification_type"] == "link_down_hint"
    assert payload["if_index"] == 38
    assert len(tasks) == 1
    tasks[0].close()


def test_mac_move_notification_is_only_a_hint_and_requests_refresh() -> None:
    receiver, events, tasks = _receiver_harness()
    receiver.coordinator.data = SimpleNamespace(
        bridge_port_ifindex={5: 51, 6: 12},
        interfaces={
            51: SimpleNamespace(
                name="GigabitEthernet1/0/17",
                description="Synthetic downstream A",
            ),
            12: SimpleNamespace(
                name="GigabitEthernet1/0/5",
                description="Synthetic downstream B",
            ),
        },
    )
    receiver._notification(
        receiver._engine,
        object(),
        Pretty("switch-engine"),
        Pretty(""),
        [
            *_notification_var_binds("1.3.6.1.4.1.9.9.215.2.0.2"),
            (Pretty("1.3.6.1.4.1.9.9.215.1.3.3.0"), Pretty("00:11:22:33:44:55")),
            (Pretty("1.3.6.1.4.1.9.9.215.1.3.4.0"), Pretty("81")),
            (Pretty("1.3.6.1.4.1.9.9.215.1.3.5.0"), Pretty("5")),
            (Pretty("1.3.6.1.4.1.9.9.215.1.3.6.0"), Pretty("6")),
        ],
        None,
    )

    assert len(events) == 1
    payload = events[0][1]
    assert payload["notification_type"] == "mac_move_hint"
    assert payload["mac_address"] == "00:11:22:33:44:55"
    assert payload["vlan"] == 81
    assert payload["from_bridge_port"] == 5
    assert payload["to_bridge_port"] == 6
    assert payload["from_if_index"] == 51
    assert payload["from_interface"] == "GigabitEthernet1/0/17"
    assert payload["from_interface_description"] == "Synthetic downstream A"
    assert payload["to_if_index"] == 12
    assert payload["to_interface"] == "GigabitEthernet1/0/5"
    assert payload["to_interface_description"] == "Synthetic downstream B"
    assert len(tasks) == 1
    tasks[0].close()


def test_mac_table_change_notification_is_only_a_refresh_hint() -> None:
    receiver, events, tasks = _receiver_harness()
    receiver._notification(
        receiver._engine,
        object(),
        Pretty("switch-engine"),
        Pretty(""),
        _notification_var_binds("1.3.6.1.4.1.9.9.215.2.0.1"),
        None,
    )

    assert len(events) == 1
    assert events[0][1]["notification_type"] == "mac_table_change_hint"
    assert len(tasks) == 1
    tasks[0].close()

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
