"""Tests for the ``jarvis agents`` CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from openjarvis.cli import cli


class TestAgentCmd:
    def test_agent_list_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "list", "--help"])
        assert result.exit_code == 0

    def test_agent_list_error_with_markup_chars_does_not_crash(self) -> None:
        """Regression for #297.

        When ``_get_manager()`` (or anything in the body) raises an
        exception whose message contains Rich markup metacharacters like
        ``[...]``, the error handler must not re-parse that text as markup
        and blow up with a secondary MarkupError traceback. The command
        should print a clean one-line error instead.
        """
        # A message with bracketed text is what triggers the MarkupError
        # when fed to console.print() unescaped.
        boom = RuntimeError("DB locked at [/var/run/x] not a [valid] tag")
        with patch("openjarvis.cli.agent_cmd._get_manager", side_effect=boom):
            result = CliRunner().invoke(cli, ["agents", "list"])
        # No traceback / unhandled exception leaked through.
        assert result.exception is None, result.output
        # The raw message (brackets intact) is surfaced to the user.
        assert "DB locked at [/var/run/x] not a [valid] tag" in result.output

    def test_agent_info_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "info", "--help"])
        assert result.exit_code == 0

    def test_agent_group_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "info" in result.output


class TestNewAgentCommands:
    def test_launch_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "launch", "--help"])
        assert result.exit_code == 0

    def test_start_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "start", "--help"])
        assert result.exit_code == 0

    def test_stop_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "stop", "--help"])
        assert result.exit_code == 0

    def test_run_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "run", "--help"])
        assert result.exit_code == 0

    def test_status_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "status", "--help"])
        assert result.exit_code == 0

    def test_logs_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "logs", "--help"])
        assert result.exit_code == 0

    def test_daemon_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "daemon", "--help"])
        assert result.exit_code == 0

    def test_watch_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "watch", "--help"])
        assert result.exit_code == 0

    def test_recover_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "recover", "--help"])
        assert result.exit_code == 0

    def test_errors_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "errors", "--help"])
        assert result.exit_code == 0

    def test_ask_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "ask", "--help"])
        assert result.exit_code == 0

    def test_instruct_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "instruct", "--help"])
        assert result.exit_code == 0

    def test_messages_help(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "messages", "--help"])
        assert result.exit_code == 0

    def test_agents_group_has_new_commands(self) -> None:
        result = CliRunner().invoke(cli, ["agents", "--help"])
        assert result.exit_code == 0
        cmds = (
            "launch",
            "start",
            "stop",
            "run",
            "status",
            "logs",
            "daemon",
            "watch",
            "recover",
            "errors",
            "ask",
            "instruct",
            "messages",
        )
        for cmd in cmds:
            assert cmd in result.output, f"Missing command: {cmd}"


class TestAgentAskApproval:
    def _invoke(self, args, executor):
        manager = MagicMock()
        manager.list_messages.return_value = []
        with (
            patch("openjarvis.cli.agent_cmd._get_manager", return_value=manager),
            patch(
                "openjarvis.cli.agent_cmd._resolve_agent_id",
                return_value="agent-1",
            ),
            patch(
                "openjarvis.cli.agent_cmd._get_scheduler_and_executor",
                return_value=(None, executor, None),
            ),
            patch("openjarvis.cli.agent_cmd._run_tick_with_live_trace"),
        ):
            return CliRunner().invoke(cli, args)

    def test_yes_uses_audited_auto_approve_callback(self) -> None:
        executor = MagicMock()
        audited = MagicMock(name="audited_callback")
        with patch(
            "openjarvis.security.approval_callback.make_audited_auto_approve_callback",
            return_value=audited,
        ) as make_callback:
            result = self._invoke(["agents", "ask", "agent-1", "hi"], executor)

        assert result.exit_code == 0, result.output
        make_callback.assert_called_once_with(
            agent_id="agent-1",
            source="cli.agent_ask",
        )
        assert executor._confirm_callback is audited

    def test_no_yes_does_not_auto_approve(self) -> None:
        executor = MagicMock()
        with patch(
            "openjarvis.security.approval_callback.make_audited_auto_approve_callback",
        ) as make_callback:
            result = self._invoke(
                ["agents", "ask", "agent-1", "hi", "--no-yes"],
                executor,
            )

        assert result.exit_code == 0, result.output
        make_callback.assert_not_called()
        assert callable(executor._confirm_callback)
