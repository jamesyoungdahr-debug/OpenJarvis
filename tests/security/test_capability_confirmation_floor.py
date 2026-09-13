"""Regression guard: any tool requiring a high-risk capability must also
require user confirmation, so this class of gap (RBAC says "dangerous" but
nothing ever asks a human) can't silently reopen when a new tool is added.
"""

from __future__ import annotations

import pytest

from openjarvis.core.registry import ToolRegistry
from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES, Capability

# Ensure all built-in tools are registered before inspecting the registry.
import openjarvis.tools  # noqa: F401,E402

_HIGH_RISK_CAPABILITIES = {Capability.SYSTEM_ADMIN.value, Capability.CHANNEL_SEND.value}


def _tools_requiring_high_risk_capability() -> list[str]:
    names = []
    for tool_name, capabilities in DEFAULT_TOOL_CAPABILITIES.items():
        if any(cap in _HIGH_RISK_CAPABILITIES for cap in capabilities):
            names.append(tool_name)
    return names


@pytest.mark.parametrize("tool_name", _tools_requiring_high_risk_capability())
def test_high_risk_capability_tools_require_confirmation(tool_name: str) -> None:
    if not ToolRegistry.contains(tool_name):
        pytest.skip(f"{tool_name} is not registered in this build")

    tool_cls = ToolRegistry.get(tool_name)
    try:
        instance = tool_cls()
    except TypeError:
        pytest.skip(
            f"{tool_name} requires constructor arguments; "
            "cannot be instantiated generically by this cross-cutting guard"
        )
        return

    assert instance.spec.requires_confirmation is True, (
        f"Tool '{tool_name}' requires a high-risk capability "
        f"({DEFAULT_TOOL_CAPABILITIES[tool_name]}) but does not require "
        "user confirmation -- this is exactly the class of gap this test "
        "exists to catch."
    )
