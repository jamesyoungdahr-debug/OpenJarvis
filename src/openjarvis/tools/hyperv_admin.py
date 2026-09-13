"""State-changing Hyper-V virtual machine actions (Windows only)."""

from __future__ import annotations

import json
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._hyperv import HyperVError, run_hyperv_json
from openjarvis.tools._stubs import BaseTool, ToolSpec

_TOOL_NAME = "hyperv_admin"
_VALID_ACTIONS = (
    "start",
    "stop",
    "turn_off",
    "save",
    "restart",
    "pause",
    "resume",
    "checkpoint",
)
_MAX_NAME_LENGTH = 100
_WILDCARD_CHARS = frozenset("*?[]")
_ACTION_TIMEOUT_SECONDS = 180.0

# Constant script. The VM name, action, and checkpoint name reach it only as
# environment variables, and the VM is matched by exact name (-eq) and passed
# as an object, so a wildcard such as "*" can never select more than one VM.
_ADMIN_SCRIPT = r"""
$name = $env:OPENJARVIS_HYPERV_VM_NAME
$action = $env:OPENJARVIS_HYPERV_ACTION
$found = @(Get-VM | Where-Object { $_.Name -eq $name })
if ($found.Count -eq 0) {
  throw "Hyper-V was unable to find a virtual machine with that name."
}
if ($found.Count -gt 1) {
  throw "More than one virtual machine has that name."
}
$vm = $found[0]
switch ($action) {
  'start' { Start-VM -VM $vm -Confirm:$false }
  'stop' { Stop-VM -VM $vm -Force -Confirm:$false }
  'turn_off' { Stop-VM -VM $vm -TurnOff -Confirm:$false }
  'save' { Save-VM -VM $vm -Confirm:$false }
  'restart' { Restart-VM -VM $vm -Force -Confirm:$false }
  'pause' { Suspend-VM -VM $vm -Confirm:$false }
  'resume' { Resume-VM -VM $vm -Confirm:$false }
  'checkpoint' {
    $checkpointName = $env:OPENJARVIS_HYPERV_CHECKPOINT_NAME
    if ($checkpointName) {
      Checkpoint-VM -VM $vm -SnapshotName $checkpointName -Confirm:$false
    } else {
      Checkpoint-VM -VM $vm -Confirm:$false
    }
  }
  default { throw "Unsupported Hyper-V action." }
}
$vm = Get-VM -Id $vm.Id
ConvertTo-Json -Compress -InputObject ([pscustomobject]@{
  name = $vm.Name
  state = [string]$vm.State
  status = [string]$vm.Status
})
"""


def _has_control_chars(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


@ToolRegistry.register("hyperv_admin")
class HyperVAdminTool(BaseTool):
    """Start, stop, save, restart, pause, resume, or checkpoint a Hyper-V VM."""

    tool_id = _TOOL_NAME
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=_TOOL_NAME,
            description=(
                "Change the state of one Hyper-V virtual machine on this Windows "
                "computer: start, stop (graceful shut down), turn_off (hard power "
                "off), save, restart, pause, resume, or checkpoint. Every call "
                "needs the user's approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(_VALID_ACTIONS),
                        "description": "What to do with the virtual machine.",
                    },
                    "name": {
                        "type": "string",
                        "maxLength": _MAX_NAME_LENGTH,
                        "description": (
                            "Exact virtual machine name (case-insensitive, no "
                            "wildcards)."
                        ),
                    },
                    "checkpoint_name": {
                        "type": "string",
                        "maxLength": _MAX_NAME_LENGTH,
                        "description": (
                            "Optional checkpoint name. Only used with the "
                            "checkpoint action."
                        ),
                    },
                },
                "required": ["action", "name"],
                "additionalProperties": False,
            },
            category="system",
            latency_estimate=10.0,
            timeout_seconds=_ACTION_TIMEOUT_SECONDS + 20.0,
            requires_confirmation=True,
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action")
        if not isinstance(action, str) or action not in _VALID_ACTIONS:
            return self._failure(f"action must be one of: {', '.join(_VALID_ACTIONS)}.")

        name_value = params.get("name")
        if not isinstance(name_value, str) or not name_value.strip():
            return self._failure("name is required.")
        name = name_value.strip()
        if len(name) > _MAX_NAME_LENGTH:
            return self._failure(f"name must be at most {_MAX_NAME_LENGTH} characters.")
        if _has_control_chars(name):
            return self._failure("name must not contain control characters.")
        if _WILDCARD_CHARS.intersection(name):
            return self._failure(
                "name must be an exact virtual machine name without wildcard "
                "characters (* ? [ ])."
            )

        values = {"ACTION": action, "VM_NAME": name}
        checkpoint_value = params.get("checkpoint_name")
        if checkpoint_value is not None:
            if action != "checkpoint":
                return self._failure(
                    "checkpoint_name is only allowed with the checkpoint action."
                )
            if not isinstance(checkpoint_value, str) or not checkpoint_value.strip():
                return self._failure("checkpoint_name must be a non-empty string.")
            checkpoint_name = checkpoint_value.strip()
            if len(checkpoint_name) > _MAX_NAME_LENGTH:
                return self._failure(
                    f"checkpoint_name must be at most {_MAX_NAME_LENGTH} characters."
                )
            if _has_control_chars(checkpoint_name):
                return self._failure(
                    "checkpoint_name must not contain control characters."
                )
            values["CHECKPOINT_NAME"] = checkpoint_name

        try:
            data = run_hyperv_json(
                _ADMIN_SCRIPT,
                values=values,
                timeout_seconds=_ACTION_TIMEOUT_SECONDS,
            )
        except HyperVError as exc:
            return self._failure(str(exc))

        if not isinstance(data, dict):
            return self._failure(
                "The Hyper-V action finished but returned an unexpected result."
            )

        payload = {
            "action": action,
            "name": data.get("name", name),
            "state": data.get("state"),
            "status": data.get("status"),
        }
        return ToolResult(
            tool_name=_TOOL_NAME,
            content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            success=True,
            metadata={"action": action, "state": payload["state"]},
        )

    @staticmethod
    def _failure(message: str) -> ToolResult:
        return ToolResult(tool_name=_TOOL_NAME, content=message, success=False)


__all__ = ["HyperVAdminTool"]
