"""ToolExecutor marks confirmation-gated tool events as sensitive."""

from __future__ import annotations

import json

from openjarvis.core.events import EventBus, EventType
from openjarvis.core.types import ToolCall, ToolResult
from openjarvis.tools._stubs import BaseTool, ToolExecutor, ToolSpec


class _GatedTool(BaseTool):
    tool_id = "gated"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="gated", description="Gated.", requires_confirmation=True)

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="gated", content="done", success=True)


class _OpenTool(BaseTool):
    tool_id = "open"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="open", description="Open.")

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="open", content="done", success=True)


def _events_for(tool_name: str) -> list:
    bus = EventBus()
    seen: list = []
    bus.subscribe(EventType.TOOL_CALL_START, seen.append)
    bus.subscribe(EventType.TOOL_CALL_END, seen.append)
    executor = ToolExecutor(
        [_GatedTool(), _OpenTool()],
        bus,
        interactive=True,
        confirm_callback=lambda _prompt: True,
    )
    executor.execute(ToolCall(id="c1", name=tool_name, arguments=json.dumps({"x": 1})))
    return seen


def test_gated_tool_events_are_sensitive():
    events = _events_for("gated")

    assert [e.event_type for e in events] == [
        EventType.TOOL_CALL_START,
        EventType.TOOL_CALL_END,
    ]
    assert all(e.data["sensitive"] is True for e in events)


def test_open_tool_events_are_not_sensitive():
    events = _events_for("open")

    assert len(events) == 2
    assert all(e.data["sensitive"] is False for e in events)
