"""Shared confirm-callback that routes ToolExecutor confirmation prompts
through the persistent, cross-process ApprovalStore instead of silently
auto-approving.

ToolExecutor's confirmation gate (tools/_stubs.py) calls a
Callable[[str], bool] synchronously from whatever thread is executing the
tool call (a ToolExecutor worker thread, an AgentExecutor tick thread, or a
CLI process thread -- never the FastAPI event loop thread directly). This
module's callback:

  1. Queues a pending_actions row via the shared ApprovalStore singleton
     (the same DB approval_routes.py and ProactiveAgent already use).
  2. Blocks the calling thread, polling the row's status.
  3. Returns True/False once a human resolves it via
     POST /v1/approvals/{id}/approve|deny, the desktop app, or
     `jarvis approvals approve|deny` -- or returns False if the wait times
     out (the row is left pending in the DB for a later out-of-band
     decision; only this particular blocked call gives up).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Optional

from openjarvis.tools.approval_store import (
    DECISION_ALWAYS_APPROVE,
    DECISION_ALWAYS_DENY,
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_PENDING,
    TIER_HIGH,
    ApprovalStore,
)

logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL_SECONDS = 1.0
_DEFAULT_TIMEOUT_SECONDS = 300.0

# Tools whose confirmation must never be short-circuited by remembered
# "always_approve" permission memory -- every call blocks on a fresh human
# decision, no exceptions. Full mouse/keyboard/screen control and Hyper-V
# VM admin are the highest-blast-radius tools in the catalog; a stale or
# socially-engineered one-time approval must not become silent standing
# access to either.
NEVER_REMEMBER_TOOLS = frozenset({"computer_use", "hyperv_admin"})

# ToolExecutor always builds the prompt as:
#   f"Allow execution of tool '{tool_call.name}' with args {params}?"
# Parse the tool name back out so the queued action has a useful
# action_type/permission_key. Falls back to the raw prompt if the format
# ever changes upstream -- never raises.
_TOOL_NAME_RE = re.compile(r"^Allow execution of tool '([^']+)'")


def extract_tool_name_from_prompt(prompt: str) -> str:
    """Parse the tool name out of ToolExecutor's confirmation prompt.

    Falls back to "unknown_tool" if the prompt doesn't match the expected
    format -- never raises.
    """
    match = _TOOL_NAME_RE.match(prompt)
    return match.group(1) if match else "unknown_tool"


def make_queued_confirm_callback(
    *,
    store: Optional[ApprovalStore] = None,
    agent_id: str = "",
    source: str = "tool_executor",
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
) -> Callable[[str], bool]:
    """Build a Callable[[str], bool] suitable for ToolExecutor(confirm_callback=...).

    Parameters
    ----------
    store:
        ApprovalStore instance to use. Defaults to a fresh ApprovalStore()
        (same SQLite file at get_config_dir()/approvals.db as every other
        caller -- WAL mode makes this safe to open per-callback).
    agent_id:
        Included in the permission_key so two different agents' pending
        confirmations for the "same" tool don't collide in permission
        memory.
    source:
        Free-text tag identifying which entry point created this callback
        (e.g. "agent_manager_routes.chat_stream", "cli.ask") -- stored in
        the queued action's payload for auditability in the approvals
        UI/API.
    timeout_seconds / poll_interval_seconds:
        How long to block and how often to poll ApprovalStore.get_action().
    """
    resolved_store = store or ApprovalStore()

    def _confirm(prompt: str) -> bool:
        tool_name = extract_tool_name_from_prompt(prompt)
        permission_key = f"tool_confirm:{agent_id or 'unknown'}:{tool_name}"

        if tool_name not in NEVER_REMEMBER_TOOLS:
            remembered = resolved_store.get_permission(permission_key)
            if remembered is not None:
                if remembered.decision == DECISION_ALWAYS_APPROVE:
                    return True
                if remembered.decision == DECISION_ALWAYS_DENY:
                    return False

        action = resolved_store.queue_action(
            action_type="tool_confirmation",
            description=prompt,
            payload={"prompt": prompt, "tool_name": tool_name, "source": source},
            permission_key=permission_key,
            tier=TIER_HIGH,
        )
        logger.info(
            "Queued approval %s for tool '%s' (agent=%s, source=%s) -- "
            "blocking up to %.0fs for a decision.",
            action.id, tool_name, agent_id, source, timeout_seconds,
        )

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            current = resolved_store.get_action(action.id)
            if current is None:
                return False
            if current.status == STATUS_APPROVED:
                return True
            if current.status == STATUS_DENIED:
                return False
            if current.status != STATUS_PENDING:
                # expired/executed -- treat as not-approved
                return False
            time.sleep(poll_interval_seconds)

        logger.warning(
            "Approval %s for tool '%s' timed out after %.0fs -- denying this "
            "call. The action remains pending in ApprovalStore for later "
            "out-of-band resolution.",
            action.id, tool_name, timeout_seconds,
        )
        return False

    return _confirm


__all__ = [
    "NEVER_REMEMBER_TOOLS",
    "extract_tool_name_from_prompt",
    "make_queued_confirm_callback",
]