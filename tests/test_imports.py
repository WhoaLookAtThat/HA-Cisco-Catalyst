"""Compatibility smoke tests for the Cisco Catalyst integration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

INTEGRATION_MODULES = (
    "custom_components.cisco_catalyst",
    "custom_components.cisco_catalyst.binary_sensor",
    "custom_components.cisco_catalyst.button",
    "custom_components.cisco_catalyst.config_flow",
    "custom_components.cisco_catalyst.const",
    "custom_components.cisco_catalyst.coordinator",
    "custom_components.cisco_catalyst.diagnostics",
    "custom_components.cisco_catalyst.trap",
    "custom_components.cisco_catalyst.entity",
    "custom_components.cisco_catalyst.sensor",
    "custom_components.cisco_catalyst.snmp",
    "custom_components.cisco_catalyst.switch",
    "custom_components.cisco_catalyst.text",
)


@pytest.mark.parametrize("module_name", INTEGRATION_MODULES)
def test_module_imports(module_name: str) -> None:
    """All integration modules import against the pinned HA release."""
    importlib.import_module(module_name)


def test_manifest_runtime_dependencies() -> None:
    """The manifest pins the SNMP runtime dependency and has a custom version."""
    manifest = json.loads(
        Path("custom_components/cisco_catalyst/manifest.json").read_text()
    )
    assert manifest["requirements"] == ["pysnmp==7.1.29"]
    assert manifest["version"]
