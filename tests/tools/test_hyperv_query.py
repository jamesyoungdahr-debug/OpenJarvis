"""Tests for the read-only Hyper-V query tool."""

from __future__ import annotations

import importlib
import json
from unittest.mock import patch

import pytest

from openjarvis.core.registry import ToolRegistry
from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES
from openjarvis.tools import hyperv_query as hyperv_query_module
from openjarvis.tools._hyperv import HyperVError
from openjarvis.tools.hyperv_query import HyperVQueryTool

_RUNNER = "openjarvis.tools.hyperv_query.run_hyperv_json"
_VMS = [
    {"name": "web-01", "state": "Running", "memory_assigned_mb": 2048},
    {"name": "Build-Box", "state": "Off", "memory_assigned_mb": 0},
]


def _payload(result):
    return json.loads(result.content)


def test_registered_read_only_without_confirmation():
    module = importlib.reload(hyperv_query_module)

    assert ToolRegistry.contains("hyperv_query")
    tool_cls = ToolRegistry.get("hyperv_query")
    assert tool_cls is module.HyperVQueryTool
    spec = tool_cls().spec
    assert spec.requires_confirmation is False
    assert spec.required_capabilities == []
    assert DEFAULT_TOOL_CAPABILITIES["hyperv_query"] == []


def test_lists_all_vms_with_a_constant_script():
    with patch(_RUNNER, return_value=_VMS) as runner:
        result = HyperVQueryTool().execute()

    assert result.success is True, result.content
    assert _payload(result) == {"count": 2, "vms": _VMS}
    assert runner.call_args.args == (hyperv_query_module._LIST_VMS_SCRIPT,)
    assert runner.call_args.kwargs == {}


def test_single_vm_object_is_normalized_to_a_list():
    with patch(_RUNNER, return_value=_VMS[0]):
        result = HyperVQueryTool().execute()

    assert _payload(result) == {"count": 1, "vms": [_VMS[0]]}


def test_no_output_means_no_vms():
    with patch(_RUNNER, return_value=None):
        result = HyperVQueryTool().execute()

    assert result.success is True
    assert _payload(result) == {"count": 0, "vms": []}


def test_name_filter_is_case_insensitive_and_never_reaches_powershell():
    with patch(_RUNNER, return_value=_VMS) as runner:
        result = HyperVQueryTool().execute(name="build-box")

    assert _payload(result)["vms"] == [_VMS[1]]
    assert "build-box" not in runner.call_args.args[0].lower()


def test_injection_style_name_is_only_a_filter():
    malicious = "x'; Remove-Item C:\\ -Recurse #"
    with patch(_RUNNER, return_value=_VMS) as runner:
        result = HyperVQueryTool().execute(name=malicious)

    assert result.success is True
    assert _payload(result)["count"] == 0
    assert malicious not in runner.call_args.args[0]


def test_running_only_filter():
    with patch(_RUNNER, return_value=_VMS):
        result = HyperVQueryTool().execute(running_only=True)

    assert _payload(result)["vms"] == [_VMS[0]]


def test_runner_error_message_is_returned():
    error = HyperVError("Hyper-V tools are only available on Windows.")
    with patch(_RUNNER, side_effect=error):
        result = HyperVQueryTool().execute()

    assert result.success is False
    assert result.content == "Hyper-V tools are only available on Windows."


def test_unexpected_output_type_fails():
    with patch(_RUNNER, return_value="not a list"):
        result = HyperVQueryTool().execute()

    assert result.success is False
    assert "unexpected" in result.content


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"name": ""}, "non-empty"),
        ({"name": 5}, "non-empty"),
        ({"name": "x" * 101}, "at most 100"),
        ({"running_only": "yes"}, "true or false"),
    ],
    ids=["empty-name", "non-string-name", "long-name", "non-bool-running-only"],
)
def test_invalid_params_rejected_without_running_powershell(params, expected):
    with patch(_RUNNER) as runner:
        result = HyperVQueryTool().execute(**params)

    assert result.success is False
    assert expected in result.content
    runner.assert_not_called()
