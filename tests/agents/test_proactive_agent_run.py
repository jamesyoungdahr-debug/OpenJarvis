"""ProactiveAgent.run executes already-approved actions and notifies the user."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from openjarvis.agents.proactive_agent import ProactiveAgent
from openjarvis.core.types import ToolCall, ToolResult
from openjarvis.tools.approval_store import (
    STATUS_APPROVED,
    TIER_MEDIUM,
    TIER_TRIVIAL,
    ApprovalStore,
)
from openjarvis.tools.proactive_tools import ExecutePendingActionsTool

_PROPOSALS = [
    {
        "action_type": "email_archive",
        "tier": TIER_TRIVIAL,
        "permission_key": "email_archive:domain:news.example.com",
        "description": "Archive newsletter",
        "payload": {"message_id": "m1"},
    },
    {
        "action_type": "email_delete",
        "tier": TIER_MEDIUM,
        "permission_key": "email_delete:domain:bob.example.com",
        "description": "Delete email from Bob",
        "payload": {"message_id": "m2"},
    },
]


@pytest.fixture
def store(tmp_path):
    approval_store = ApprovalStore(db_path=str(tmp_path / "approvals.db"))
    yield approval_store
    approval_store.close()


def _run(store, tmp_path, *, send_ok=True):
    agent = ProactiveAgent(MagicMock(), "test-model", approval_store=store)
    agent._notification_destination = "user-1"
    channel = MagicMock()
    channel.send.return_value = send_ok
    tools = agent._executor._tools
    tools["channel_send"]._channel = channel
    with (
        patch.object(
            tools["digest_collect"],
            "execute",
            return_value=ToolResult(
                tool_name="digest_collect", content="2 new emails", success=True
            ),
        ),
        patch.object(
            ExecutePendingActionsTool, "_run_action", return_value=(True, "done")
        ),
        patch.object(
            agent, "_generate", return_value={"content": json.dumps(_PROPOSALS)}
        ),
        patch("openjarvis.core.config.DEFAULT_CONFIG_DIR", tmp_path),
    ):
        result = agent.run()
    return agent, channel, result


def _rows(store):
    query = (
        "SELECT action_type, status, notification_sent, payload FROM pending_actions"
    )
    return [
        {
            "action_type": row[0],
            "status": row[1],
            "notification_sent": bool(row[2]),
            "payload": json.loads(row[3]) if row[3] else {},
        }
        for row in store._conn.execute(query).fetchall()
    ]


def test_run_executes_approved_actions_and_notifies(store, tmp_path):
    _, channel, _ = _run(store, tmp_path)

    rows = _rows(store)
    archive = next(r for r in rows if r["action_type"] == "email_archive")
    delete = next(r for r in rows if r["action_type"] == "email_delete")
    assert archive["status"] == "executed"
    assert delete["status"] == "pending"
    assert delete["notification_sent"] is True
    channel.send.assert_called_once()


def test_internal_steps_are_recorded_as_audited_approvals(store, tmp_path):
    _run(store, tmp_path)

    audits = [r for r in _rows(store) if r["action_type"] == "tool_confirmation"]
    assert sorted(r["payload"]["tool_name"] for r in audits) == [
        "channel_send",
        "execute_pending_actions",
    ]
    assert all(r["status"] == "approved" for r in audits)
    assert all(r["payload"]["source"] == "proactive_agent.run" for r in audits)


def test_failed_notification_is_not_marked_sent(store, tmp_path):
    _, channel, _ = _run(store, tmp_path, send_ok=False)

    delete = next(r for r in _rows(store) if r["action_type"] == "email_delete")
    assert delete["notification_sent"] is False
    channel.send.assert_called_once()


def test_model_facing_executor_stays_gated(store, tmp_path):
    agent, _, _ = _run(store, tmp_path)

    for name, arguments in [
        ("execute_pending_actions", {}),
        ("channel_send", {"channel": "user-1", "content": "hi"}),
        ("record_decision", {"action_id": "x", "approved": True}),
    ]:
        result = agent._executor.execute(
            ToolCall(id=name, name=name, arguments=json.dumps(arguments))
        )
        assert result.success is False
        assert "requires confirmation" in result.content


def test_execute_pending_actions_never_runs_tool_confirmation_rows(store):
    action = store.queue_action(
        action_type="tool_confirmation",
        description="Allow execution of tool 'file_write' with args {}?",
        payload={"tool_name": "file_write"},
        permission_key="tool_confirm:agent:file_write",
        tier="high",
    )
    store.update_status(action.id, STATUS_APPROVED)
    tool = ExecutePendingActionsTool(store=store)

    with patch.object(ExecutePendingActionsTool, "_run_action") as run_action:
        result = tool.execute()

    run_action.assert_not_called()
    assert result.success is True
    assert json.loads(result.content) == []
    assert store.get_action(action.id).status == "approved"
