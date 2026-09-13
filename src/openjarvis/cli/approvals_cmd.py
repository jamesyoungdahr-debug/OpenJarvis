"""``jarvis approvals`` — review and resolve queued tool approvals."""

from __future__ import annotations

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from openjarvis.tools.approval_store import (
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_PENDING,
    ApprovalStore,
)


def _get_store() -> ApprovalStore:
    return ApprovalStore()


@click.group()
def approvals() -> None:
    """Review and resolve tool actions waiting for your approval."""


@approvals.command("list")
def list_approvals() -> None:
    """List actions waiting for approval."""
    console = Console()
    store = _get_store()
    try:
        store.expire_stale()
        pending = store.list_pending()
    finally:
        store.close()

    if not pending:
        console.print("[dim]No actions waiting for approval.[/dim]")
        return

    table = Table(title="Pending Approvals")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Tool", style="yellow")
    table.add_column("Source", style="magenta")
    table.add_column("Description", style="green", max_width=60)
    table.add_column("Created", style="dim")
    for action in pending:
        table.add_row(
            action.id,
            escape(str(action.payload.get("tool_name", action.action_type))),
            escape(str(action.payload.get("source", ""))),
            escape(action.description),
            action.created_at[:19],
        )
    console.print(table)
    console.print(f"\n[dim]Total: {len(pending)} pending[/dim]")


def _resolve(action_id: str, status: str, verb: str) -> None:
    console = Console()
    store = _get_store()
    try:
        store.expire_stale()
        action = store.get_action(action_id)
        if action is None:
            console.print(f"[red]No approval found with ID {escape(action_id)}.[/red]")
            raise SystemExit(1)
        if action.status != STATUS_PENDING:
            console.print(
                f"[red]Approval {escape(action_id)} is already "
                f"{escape(action.status)}; only pending approvals can be "
                "changed.[/red]"
            )
            raise SystemExit(1)
        store.update_status(action_id, status)
    finally:
        store.close()
    console.print(
        f"[green]{verb} {escape(action_id)}:[/green] {escape(action.description)}"
    )


@approvals.command()
@click.argument("action_id")
def approve(action_id: str) -> None:
    """Approve a pending action by ID."""
    _resolve(action_id, STATUS_APPROVED, "Approved")


@approvals.command()
@click.argument("action_id")
def deny(action_id: str) -> None:
    """Deny a pending action by ID."""
    _resolve(action_id, STATUS_DENIED, "Denied")


__all__ = ["approvals"]
