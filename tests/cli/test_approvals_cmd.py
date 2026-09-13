"""Tests for the ``jarvis approvals`` CLI commands."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from openjarvis.cli import cli
from openjarvis.tools.approval_store import (
    STATUS_APPROVED,
    STATUS_DENIED,
    TIER_HIGH,
    ApprovalStore,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "approvals.db")
    with patch(
        "openjarvis.cli.approvals_cmd._get_store",
        side_effect=lambda: ApprovalStore(db_path=path),
    ):
        yield path


def _queue(db_path: str, tool_name: str = "file_write") -> str:
    store = ApprovalStore(db_path=db_path)
    try:
        action = store.queue_action(
            action_type="tool_confirmation",
            description=f"Allow execution of tool '{tool_name}' with args {{}}?",
            payload={"tool_name": tool_name, "source": "cli.ask"},
            permission_key=f"tool_confirm:agent-a:{tool_name}",
            tier=TIER_HIGH,
        )
    finally:
        store.close()
    return action.id


def _status(db_path: str, action_id: str) -> str:
    store = ApprovalStore(db_path=db_path)
    try:
        return store.get_action(action_id).status
    finally:
        store.close()


def test_approvals_registered_on_cli():
    result = CliRunner().invoke(cli, ["approvals", "--help"])
    assert result.exit_code == 0, result.output
    for cmd in ("list", "approve", "deny"):
        assert cmd in result.output


def test_list_shows_pending_actions(db_path):
    action_id = _queue(db_path, "file_write")

    result = CliRunner().invoke(cli, ["approvals", "list"])

    assert result.exit_code == 0, result.output
    assert action_id in result.output
    assert "file_write" in result.output


def test_list_with_nothing_pending(db_path):
    result = CliRunner().invoke(cli, ["approvals", "list"])

    assert result.exit_code == 0, result.output
    assert "No actions waiting for approval" in result.output


def test_approve_marks_action_approved(db_path):
    action_id = _queue(db_path)

    result = CliRunner().invoke(cli, ["approvals", "approve", action_id])

    assert result.exit_code == 0, result.output
    assert _status(db_path, action_id) == STATUS_APPROVED


def test_deny_marks_action_denied(db_path):
    action_id = _queue(db_path)

    result = CliRunner().invoke(cli, ["approvals", "deny", action_id])

    assert result.exit_code == 0, result.output
    assert _status(db_path, action_id) == STATUS_DENIED


def test_unknown_id_exits_nonzero(db_path):
    result = CliRunner().invoke(cli, ["approvals", "approve", "doesnotexist"])

    assert result.exit_code == 1
    assert "No approval found" in result.output


def test_resolved_action_cannot_be_flipped(db_path):
    action_id = _queue(db_path)
    CliRunner().invoke(cli, ["approvals", "deny", action_id])

    result = CliRunner().invoke(cli, ["approvals", "approve", action_id])

    assert result.exit_code == 1
    assert "already denied" in result.output
    assert _status(db_path, action_id) == STATUS_DENIED
