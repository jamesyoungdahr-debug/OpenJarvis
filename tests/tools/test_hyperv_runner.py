"""Tests for the shared Hyper-V PowerShell runner."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from openjarvis.tools import _hyperv

# Reach HyperVError and run_hyperv_json through the module, not imported names:
# other tests reload every openjarvis.tools module, which replaces HyperVError
# with a new class that an imported name would no longer match.

_RUN = "openjarvis.tools._hyperv.subprocess.run"
_PLATFORM = "openjarvis.tools._hyperv.sys.platform"


def _completed(returncode=0, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_non_windows_fails_without_running_powershell():
    with patch(_PLATFORM, "linux"), patch(_RUN) as run:
        with pytest.raises(_hyperv.HyperVError, match="only available on Windows"):
            _hyperv.run_hyperv_json("Get-VM")

    run.assert_not_called()


def test_parses_json_output():
    with (
        patch(_PLATFORM, "win32"),
        patch(_RUN, return_value=_completed(stdout=b'[{"name":"vm1"}]')),
    ):
        assert _hyperv.run_hyperv_json("Get-VM") == [{"name": "vm1"}]


def test_command_shape_and_hidden_window():
    with (
        patch(_PLATFORM, "win32"),
        patch(_RUN, return_value=_completed(stdout=b"[]")) as run,
    ):
        _hyperv.run_hyperv_json("Get-VM", timeout_seconds=12)

    command = run.call_args.args[0]
    assert command[:4] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]
    assert command[4].startswith("[Console]::OutputEncoding")
    assert command[4].endswith("Get-VM")
    kwargs = run.call_args.kwargs
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == 12
    assert kwargs["check"] is False
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_values_travel_only_through_environment():
    malicious = "x'; Remove-Item C:\\ -Recurse #"
    with (
        patch(_PLATFORM, "win32"),
        patch(_RUN, return_value=_completed(stdout=b"[]")) as run,
    ):
        _hyperv.run_hyperv_json(
            "Get-VM -Name $env:OPENJARVIS_HYPERV_VM_NAME",
            values={"VM_NAME": malicious},
        )

    assert malicious not in " ".join(run.call_args.args[0])
    assert run.call_args.kwargs["env"]["OPENJARVIS_HYPERV_VM_NAME"] == malicious


def test_stale_prefixed_environment_values_are_removed():
    with (
        patch.dict(os.environ, {"OPENJARVIS_HYPERV_STALE": "leftover"}),
        patch(_PLATFORM, "win32"),
        patch(_RUN, return_value=_completed(stdout=b"[]")) as run,
    ):
        _hyperv.run_hyperv_json("Get-VM")

    assert "OPENJARVIS_HYPERV_STALE" not in run.call_args.kwargs["env"]


@pytest.mark.parametrize(
    "values",
    [
        {"vm name": "x"},
        {"lower": "x"},
        {"VM_NAME": "bad\x00value"},
        {"VM_NAME": 5},
    ],
    ids=["space-in-name", "lowercase-name", "nul-in-value", "non-string-value"],
)
def test_invalid_values_rejected_before_running(values):
    with patch(_PLATFORM, "win32"), patch(_RUN) as run:
        with pytest.raises(ValueError):
            _hyperv.run_hyperv_json("Get-VM", values=values)

    run.assert_not_called()


def test_empty_output_returns_none():
    with patch(_PLATFORM, "win32"), patch(_RUN, return_value=_completed(stdout=b"  ")):
        assert _hyperv.run_hyperv_json("Get-VM") is None


def test_invalid_json_raises():
    with (
        patch(_PLATFORM, "win32"),
        patch(_RUN, return_value=_completed(stdout=b"not json")),
    ):
        with pytest.raises(_hyperv.HyperVError, match="not valid JSON"):
            _hyperv.run_hyperv_json("Get-VM")


def test_oversized_output_raises():
    big = b"[" + b"1," * (_hyperv._MAX_OUTPUT_BYTES // 2) + b"1]"
    with patch(_PLATFORM, "win32"), patch(_RUN, return_value=_completed(stdout=big)):
        with pytest.raises(_hyperv.HyperVError, match="too much output"):
            _hyperv.run_hyperv_json("Get-VM")


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (b"Get-VM : The term 'Get-VM' is not recognized as the name", "not installed"),
        (
            b"You do not have the required permission to complete this task.",
            "denied access",
        ),
        (
            b"Hyper-V was unable to find a virtual machine with name 'x'.",
            "No virtual machine",
        ),
        (b"something else broke", "exit code 1"),
    ],
    ids=["module-missing", "permission", "vm-not-found", "other"],
)
def test_failures_are_classified(stderr, expected):
    with (
        patch(_PLATFORM, "win32"),
        patch(_RUN, return_value=_completed(returncode=1, stderr=stderr)),
    ):
        with pytest.raises(_hyperv.HyperVError, match=expected):
            _hyperv.run_hyperv_json("Get-VM")


def test_missing_powershell_raises():
    with patch(_PLATFORM, "win32"), patch(_RUN, side_effect=FileNotFoundError()):
        with pytest.raises(_hyperv.HyperVError, match="was not found"):
            _hyperv.run_hyperv_json("Get-VM")


def test_timeout_raises():
    error = subprocess.TimeoutExpired(cmd="powershell.exe", timeout=5)
    with patch(_PLATFORM, "win32"), patch(_RUN, side_effect=error):
        with pytest.raises(_hyperv.HyperVError, match="timed out"):
            _hyperv.run_hyperv_json("Get-VM", timeout_seconds=5)
