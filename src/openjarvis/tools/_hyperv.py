"""Shared PowerShell runner for the Hyper-V tools (Windows only)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

_ENV_PREFIX = "OPENJARVIS_HYPERV_"
_VALUE_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_MAX_OUTPUT_BYTES = 1_000_000
_SCRIPT_PREAMBLE = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
    "$ErrorActionPreference = 'Stop'\n"
)


class HyperVError(RuntimeError):
    """A Hyper-V PowerShell call failed; the message is safe to show the user."""


def _build_env(values: Mapping[str, str] | None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(_ENV_PREFIX)
    }
    for name, value in (values or {}).items():
        if not isinstance(name, str) or not _VALUE_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"Invalid Hyper-V value name: {name!r}")
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError(f"Hyper-V value {name} must be a string without NUL.")
        env[f"{_ENV_PREFIX}{name}"] = value
    return env


def _classify_failure(stderr: str, returncode: int) -> str:
    text = stderr.lower()
    if "is not recognized" in text or "commandnotfoundexception" in text:
        return (
            "The Hyper-V PowerShell module is not installed, or Hyper-V is not "
            "enabled on this computer."
        )
    if (
        "required permission" in text
        or "access is denied" in text
        or "unauthorizedaccess" in text
    ):
        return (
            "Hyper-V denied access. Run OpenJarvis as an administrator or add your "
            "account to the Hyper-V Administrators group."
        )
    if "unable to find a virtual machine" in text:
        return "No virtual machine with that name was found."
    return f"The Hyper-V command failed (PowerShell exit code {returncode})."


def run_hyperv_json(
    script: str,
    *,
    values: Mapping[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> Any:
    """Run a constant PowerShell *script* and return its parsed JSON output.

    ``script`` must never contain caller-supplied data. Pass that data through
    ``values`` instead: each entry is exposed to the script only as
    ``$env:OPENJARVIS_HYPERV_<NAME>``, so PowerShell never parses it as code.
    Returns ``None`` when the script prints nothing.
    """
    if sys.platform != "win32":
        raise HyperVError("Hyper-V tools are only available on Windows.")

    env = _build_env(values)
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        _SCRIPT_PREAMBLE + script,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_seconds,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except FileNotFoundError as exc:
        raise HyperVError("PowerShell (powershell.exe) was not found.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HyperVError(
            f"The Hyper-V command timed out after {timeout_seconds:g} seconds."
        ) from exc
    except OSError as exc:
        raise HyperVError(
            f"Could not start PowerShell ({type(exc).__name__})."
        ) from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
        raise HyperVError(_classify_failure(stderr, completed.returncode))

    raw_stdout = completed.stdout or b""
    if len(raw_stdout) > _MAX_OUTPUT_BYTES:
        raise HyperVError("The Hyper-V command returned too much output.")
    stdout = raw_stdout.decode("utf-8", errors="replace").strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise HyperVError(
            "The Hyper-V command returned output that is not valid JSON."
        ) from exc


__all__ = ["HyperVError", "run_hyperv_json"]
