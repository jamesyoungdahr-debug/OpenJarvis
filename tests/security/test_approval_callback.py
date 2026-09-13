"""Tests for the shared queued confirm-callback."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from openjarvis.security.approval_callback import (
    NEVER_REMEMBER_TOOLS,
    extract_tool_name_from_prompt,
    make_queued_confirm_callback,
)
from openjarvis.tools.approval_store import (
    DECISION_ALWAYS_APPROVE,
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_PENDING,
    ApprovalStore,
)


def _make_store(tmp_path) -> ApprovalStore:
    return ApprovalStore(db_path=str(tmp_path / "approvals.db"))


def _prompt(tool_name: str) -> str:
    return f"Allow execution of tool '{tool_name}' with args {{}}?"


def test_extract_tool_name_from_prompt_matches_expected_format():
    assert extract_tool_name_from_prompt("Allow execution of tool 'shell_exec' with args {'command': 'ls'}?") == "shell_exec"


def test_extract_tool_name_from_prompt_falls_back_on_malformed_input():
    assert extract_tool_name_from_prompt("this is not a real prompt") == "unknown_tool"


def test_approve_via_store_from_another_thread_returns_true(tmp_path):
    store = _make_store(tmp_path)
    confirm = make_queued_confirm_callback(store=store, timeout_seconds=5, poll_interval_seconds=0.05)

    result_holder = {}

    def _run():
        result_holder["result"] = confirm(_prompt("file_write"))

    thread = threading.Thread(target=_run)
    thread.start()

    # Wait for the action to be queued, then approve it.
    action_id = None
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and action_id is None:
        pending = store.list_pending()
        if pending:
            action_id = pending[0].id
        else:
            time.sleep(0.02)
    assert action_id is not None
    store.update_status(action_id, STATUS_APPROVED)

    thread.join(timeout=3)
    assert result_holder["result"] is True


def test_deny_via_store_returns_false(tmp_path):
    store = _make_store(tmp_path)
    confirm = make_queued_confirm_callback(store=store, timeout_seconds=5, poll_interval_seconds=0.05)

    result_holder = {}

    def _run():
        result_holder["result"] = confirm(_prompt("shell_exec"))

    thread = threading.Thread(target=_run)
    thread.start()

    action_id = None
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and action_id is None:
        pending = store.list_pending()
        if pending:
            action_id = pending[0].id
        else:
            time.sleep(0.02)
    assert action_id is not None
    store.update_status(action_id, STATUS_DENIED)

    thread.join(timeout=3)
    assert result_holder["result"] is False


def test_timeout_denies_and_leaves_action_pending(tmp_path):
    store = _make_store(tmp_path)
    confirm = make_queued_confirm_callback(store=store, timeout_seconds=0.2, poll_interval_seconds=0.05)

    result = confirm(_prompt("apply_patch"))

    assert result is False
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].status == STATUS_PENDING


def test_remembered_always_approve_short_circuits_without_queuing(tmp_path):
    store = _make_store(tmp_path)
    permission_key = "tool_confirm:unknown:git_commit"
    store.set_permission(permission_key, DECISION_ALWAYS_APPROVE, approved=True)

    confirm = make_queued_confirm_callback(store=store, timeout_seconds=5, poll_interval_seconds=0.05)
    result = confirm(_prompt("git_commit"))

    assert result is True
    assert store.list_pending() == []


def test_never_remember_tools_ignore_remembered_always_approve(tmp_path):
    store = _make_store(tmp_path)
    for tool_name in NEVER_REMEMBER_TOOLS:
        permission_key = f"tool_confirm:unknown:{tool_name}"
        store.set_permission(permission_key, DECISION_ALWAYS_APPROVE, approved=True)

        confirm = make_queued_confirm_callback(store=store, timeout_seconds=0.2, poll_interval_seconds=0.05)
        result = confirm(_prompt(tool_name))

        # Not remembered -- times out (nobody resolves it), proving it was
        # actually queued and blocked rather than short-circuited to True.
        assert result is False
        pending = store.list_pending()
        assert any(p.permission_key == permission_key for p in pending)


def test_permission_key_includes_agent_id(tmp_path):
    store = _make_store(tmp_path)
    confirm_a = make_queued_confirm_callback(store=store, agent_id="agent-a", timeout_seconds=0.2, poll_interval_seconds=0.05)
    confirm_b = make_queued_confirm_callback(store=store, agent_id="agent-b", timeout_seconds=0.2, poll_interval_seconds=0.05)

    confirm_a(_prompt("file_write"))
    confirm_b(_prompt("file_write"))

    keys = {p.permission_key for p in store.list_pending()}
    assert "tool_confirm:agent-a:file_write" in keys
    assert "tool_confirm:agent-b:file_write" in keys