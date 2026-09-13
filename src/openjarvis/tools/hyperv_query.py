"""Read-only Hyper-V virtual machine listing (Windows only)."""

from __future__ import annotations

import json
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._hyperv import HyperVError, run_hyperv_json
from openjarvis.tools._stubs import BaseTool, ToolSpec

_TOOL_NAME = "hyperv_query"
_MAX_NAME_LENGTH = 100
_LIST_VMS_SCRIPT = """\
$vms = @(Get-VM | ForEach-Object {
  [pscustomobject]@{
    name = $_.Name
    state = [string]$_.State
    status = [string]$_.Status
    cpu_usage_percent = $_.CPUUsage
    memory_assigned_mb = [math]::Round($_.MemoryAssigned / 1MB)
    uptime_seconds = [int]$_.Uptime.TotalSeconds
    generation = $_.Generation
    version = [string]$_.Version
  }
})
ConvertTo-Json -InputObject $vms -Compress -Depth 3
"""


@ToolRegistry.register("hyperv_query")
class HyperVQueryTool(BaseTool):
    """List Hyper-V virtual machines and their current state."""

    tool_id = _TOOL_NAME
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=_TOOL_NAME,
            description=(
                "List the Hyper-V virtual machines on this Windows computer with "
                "their state, CPU usage, memory, and uptime. Read-only."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "maxLength": _MAX_NAME_LENGTH,
                        "description": (
                            "Only return the virtual machine with this exact name "
                            "(case-insensitive)."
                        ),
                    },
                    "running_only": {
                        "type": "boolean",
                        "description": "Only return running virtual machines.",
                    },
                },
                "additionalProperties": False,
            },
            category="system",
            latency_estimate=2.0,
            timeout_seconds=45.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        name = params.get("name")
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                return self._failure("name must be a non-empty string.")
            name = name.strip()
            if len(name) > _MAX_NAME_LENGTH:
                return self._failure(
                    f"name must be at most {_MAX_NAME_LENGTH} characters."
                )

        running_only = params.get("running_only", False)
        if not isinstance(running_only, bool):
            return self._failure("running_only must be true or false.")

        try:
            data = run_hyperv_json(_LIST_VMS_SCRIPT)
        except HyperVError as exc:
            return self._failure(str(exc))

        if data is None:
            data = []
        elif isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return self._failure("The Hyper-V query returned an unexpected result.")

        vms = [vm for vm in data if isinstance(vm, dict)]
        if name is not None:
            wanted = name.casefold()
            vms = [vm for vm in vms if str(vm.get("name", "")).casefold() == wanted]
        if running_only:
            vms = [vm for vm in vms if str(vm.get("state", "")).casefold() == "running"]

        return ToolResult(
            tool_name=_TOOL_NAME,
            content=json.dumps(
                {"count": len(vms), "vms": vms},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            success=True,
            metadata={"count": len(vms)},
        )

    @staticmethod
    def _failure(message: str) -> ToolResult:
        return ToolResult(tool_name=_TOOL_NAME, content=message, success=False)


__all__ = ["HyperVQueryTool"]
