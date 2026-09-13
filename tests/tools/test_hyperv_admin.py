"""Tests for the state-changing Hyper-V admin tool."""

from __future__ import annotations

import importlib
import json
from unittest.mock import patch

import pytest

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolCall
from openjarvis.security.approval_callback import NEVER_REMEMBER_TOOLS
from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES, Capability
from openjarvis.tools import hyperv_admin as hyperv_admin_module
from openjarvis.tools._hyperv import HyperVError
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.hyperv_admin import HyperVAdminTool

_RUNNER = "openjarvis.tools.hyperv_admin.run_hyperv_json"
_RESULT = {"name": "web-01", "state": "Running", "status": "Operating normally"}


def test_registered_as_admin_confirming_and_never_remembered():
    module = importlib.reload(hyperv_admin_module)

    assert ToolRegistry.contains("hyperv_admin")
    tool_cls = ToolRegistry.get("hyperv_admin")
    assert tool_cls is module.HyperVAdminTool
    spec = tool_cls().spec
    assert spec.requires_confirmation is True
    assert spec.required_capabilities == ["system:admin"]
    assert DEFAULT_TOOL_CAPABILITIES["hyperv_admin"] == [Capability.SYSTEM_ADMIN]
    assert "hyperv_admin" in NEVER_REMEMBER_TOOLS
    assert spec.parameters["required"] == ["action", "name"]


@pytest.mark.parametrize(
    "action",
    ["start", "stop", "turn_off", "save", "restart", "pause", "resume", "checkpoint"],
)
def test_each_action_runs_the_constant_script_with_env_values(action):
    with patch(_RUNNER, return_value=_RESULT) as runner:
        result = HyperVAdminTool().execute(action=action, name="web-01")

    assert result.success is True, result.content
    assert json.loads(result.content) == {
        "action": action,
        "name": "web-01",
        "state": "Running",
        "status": "Operating normally",
    }
    assert runner.call_args.args == (hyperv_admin_module._ADMIN_SCRIPT,)
    assert runner.call_args.kwargs["values"] == {"ACTION": action, "VM_NAME": "web-01"}
    assert (
        runner.call_args.kwargs["timeout_seconds"]
        == hyperv_admin_module._ACTION_TIMEOUT_SECONDS
    )


def test_checkpoint_name_is_passed_as_a_value():
    with patch(_RUNNER, return_value=_RESULT) as runner:
        result = HyperVAdminTool().execute(
            action="checkpoint", name="web-01", checkpoint_name="before update"
        )

    assert result.success is True, result.content
    assert runner.call_args.kwargs["values"] == {
        "ACTION": "checkpoint",
        "VM_NAME": "web-01",
        "CHECKPOINT_NAME": "before update",
    }


def test_injection_style_name_never_enters_the_script():
    malicious = "x'; Remove-Item C:\\ -Recurse #"
    with patch(_RUNNER, return_value=_RESULT) as runner:
        HyperVAdminTool().execute(action="start", name=malicious)

    script = runner.call_args.args[0]
    assert script == hyperv_admin_module._ADMIN_SCRIPT
    assert malicious not in script
    assert runner.call_args.kwargs["values"]["VM_NAME"] == malicious


def test_script_matches_vm_by_exact_name_not_wildcard_name_parameter():
    script = hyperv_admin_module._ADMIN_SCRIPT

    assert "-eq $name" in script
    assert "-Name $" not in script
    assert "$env:OPENJARVIS_HYPERV_VM_NAME" in script


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"name": "web-01"}, "action must be one of"),
        ({"action": "delete", "name": "web-01"}, "action must be one of"),
        ({"action": "start"}, "name is required"),
        ({"action": "start", "name": "   "}, "name is required"),
        ({"action": "start", "name": "x" * 101}, "at most 100"),
        ({"action": "start", "name": "web\x0001"}, "control characters"),
        ({"action": "start", "name": "*"}, "wildcard"),
        ({"action": "start", "name": "web-?"}, "wildcard"),
        ({"action": "start", "name": "[w]eb"}, "wildcard"),
        (
            {"action": "start", "name": "web-01", "checkpoint_name": "cp"},
            "only allowed with the checkpoint action",
        ),
        (
            {"action": "checkpoint", "name": "web-01", "checkpoint_name": ""},
            "non-empty",
        ),
        (
            {"action": "checkpoint", "name": "web-01", "checkpoint_name": "c" * 101},
            "at most 100",
        ),
        (
            {"action": "checkpoint", "name": "web-01", "checkpoint_name": "a\nb"},
            "control characters",
        ),
    ],
    ids=[
        "missing-action",
        "unknown-action",
        "missing-name",
        "blank-name",
        "long-name",
        "control-char-name",
        "star-wildcard",
        "question-wildcard",
        "bracket-wildcard",
        "checkpoint-name-wrong-action",
        "empty-checkpoint-name",
        "long-checkpoint-name",
        "control-char-checkpoint-name",
    ],
)
def test_invalid_params_rejected_without_running_powershell(params, expected):
    with patch(_RUNNER) as runner:
        result = HyperVAdminTool().execute(**params)

    assert result.success is False
    assert expected in result.content
    runner.assert_not_called()


def test_runner_error_message_is_returned():
    error = HyperVError("No virtual machine with that name was found.")
    with patch(_RUNNER, side_effect=error):
        result = HyperVAdminTool().execute(action="start", name="missing")

    assert result.success is False
    assert result.content == "No virtual machine with that name was found."


@pytest.mark.parametrize("output", [None, [], "Running"], ids=["none", "list", "str"])
def test_unexpected_output_is_reported(output):
    with patch(_RUNNER, return_value=output):
        result = HyperVAdminTool().execute(action="start", name="web-01")

    assert result.success is False
    assert "unexpected result" in result.content


@pytest.mark.parametrize("confirmed", [False, None], ids=["denied", "non-interactive"])
def test_executor_blocks_admin_action_without_approval(confirmed):
    if confirmed is None:
        executor = ToolExecutor([HyperVAdminTool()], interactive=False)
    else:
        executor = ToolExecutor(
            [HyperVAdminTool()],
            interactive=True,
            confirm_callback=lambda _prompt: confirmed,
        )

    with patch(_RUNNER) as runner:
        result = executor.execute(
            ToolCall(
                id="vm",
                name="hyperv_admin",
                arguments=json.dumps({"action": "turn_off", "name": "web-01"}),
            )
        )

    assert result.success is False
    runner.assert_not_called()
