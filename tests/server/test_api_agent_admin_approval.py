"""Agent admin API calls approve confirmation-gated tools with an audit record."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.core.types import ToolResult  # noqa: E402
from openjarvis.security.runtime import execute_secured_tool  # noqa: E402
from openjarvis.server.api_routes import include_all_routes  # noqa: E402
from openjarvis.tools._stubs import BaseTool, ToolSpec  # noqa: E402
from openjarvis.tools.approval_store import ApprovalStore  # noqa: E402


class _GatedTool(BaseTool):
    tool_id = "gated_admin"

    def __init__(self) -> None:
        self.calls = 0

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="gated_admin", description="Gated.", requires_confirmation=True
        )

    def execute(self, **params) -> ToolResult:
        self.calls += 1
        return ToolResult(tool_name="gated_admin", content="ran", success=True)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    return tmp_path


def _audit_rows(home):
    store = ApprovalStore(db_path=str(home / "approvals.db"))
    try:
        return [
            action
            for action in store.list_approved()
            if action.action_type == "tool_confirmation"
        ]
    finally:
        store.close()


def test_execute_secured_tool_fails_closed_without_callback():
    tool = _GatedTool()

    result = execute_secured_tool(tool, {}, agent_id="server:api")

    assert result.success is False
    assert "requires confirmation" in result.content
    assert tool.calls == 0


def test_execute_secured_tool_runs_gated_tool_with_callback():
    tool = _GatedTool()
    prompts = []

    result = execute_secured_tool(
        tool,
        {},
        agent_id="server:api",
        confirm_callback=lambda prompt: prompts.append(prompt) or True,
    )

    assert result.success is True
    assert tool.calls == 1
    assert prompts and "gated_admin" in prompts[0]


def test_create_and_kill_agent_are_approved_and_audited(home):
    from openjarvis.tools.agent_tools import _SPAWNED_AGENTS

    app = FastAPI()
    include_all_routes(app)
    client = TestClient(app)
    _SPAWNED_AGENTS.pop("audited-api-agent", None)
    try:
        created = client.post(
            "/v1/agents",
            json={"agent_type": "simple", "agent_id": "audited-api-agent"},
        )
        assert created.status_code == 200, created.text
        assert "audited-api-agent" in _SPAWNED_AGENTS

        killed = client.delete("/v1/agents/audited-api-agent")
        assert killed.status_code == 200, killed.text
    finally:
        _SPAWNED_AGENTS.pop("audited-api-agent", None)

    rows = _audit_rows(home)
    assert sorted(row.payload["tool_name"] for row in rows) == [
        "agent_kill",
        "agent_spawn",
    ]
    assert all(row.payload["source"] == "api_routes.agent_admin" for row in rows)
    assert all(row.payload["auto_approved"] is True for row in rows)


def test_listing_agents_writes_no_approval_rows(home):
    app = FastAPI()
    include_all_routes(app)

    resp = TestClient(app).get("/v1/agents")

    assert resp.status_code == 200
    assert _audit_rows(home) == []
