"""Tests for integration-level entity registry migrations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.cisco_catalyst import _remove_legacy_access_vlan_number_entities


def test_remove_legacy_access_vlan_number_entities_only_removes_old_number_entities() -> None:
    registry = SimpleNamespace(async_remove=Mock())
    entries = [
        SimpleNamespace(
            domain="number",
            platform="cisco_catalyst",
            unique_id="192.0.2.10_if_44_access_vlan",
            entity_id="number.gigabitethernet1_0_37_gigabitethernet1_0_37_access_vlan",
        ),
        SimpleNamespace(
            domain="select",
            platform="cisco_catalyst",
            unique_id="192.0.2.10_if_44_access_vlan",
            entity_id="select.gigabitethernet1_0_37_access_vlan",
        ),
        SimpleNamespace(
            domain="number",
            platform="other_integration",
            unique_id="192.0.2.10_if_44_access_vlan",
            entity_id="number.other_access_vlan",
        ),
        SimpleNamespace(
            domain="number",
            platform="cisco_catalyst",
            unique_id="192.0.2.10_if_44_other",
            entity_id="number.other",
        ),
    ]
    entry = SimpleNamespace(entry_id="entry-1")

    with (
        patch(
            "custom_components.cisco_catalyst.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.cisco_catalyst.er.async_entries_for_config_entry",
            return_value=entries,
        ),
    ):
        _remove_legacy_access_vlan_number_entities(SimpleNamespace(), entry)

    registry.async_remove.assert_called_once_with(
        "number.gigabitethernet1_0_37_gigabitethernet1_0_37_access_vlan"
    )
