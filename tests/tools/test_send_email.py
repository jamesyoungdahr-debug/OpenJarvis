"""Tests for the send_email tool."""

from __future__ import annotations

import base64
import importlib
import json
import smtplib
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from openjarvis.core.credentials import TOOL_CREDENTIALS, is_credential_optional
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolCall
from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES, Capability
from openjarvis.tools import send_email as send_email_module
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.send_email import SendEmailTool

_MODULE = "openjarvis.tools.send_email"
_GOOD = {"to": ["alice@example.com"], "subject": "Hello", "body": "Hi Alice."}


def _config(**overrides):
    values = {
        "backend": "smtp",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "from_address": "me@example.com",
        "max_recipients": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _credentials(username="me@example.com", password="app-password"):
    values = {"SMTP_USERNAME": username, "SMTP_PASSWORD": password}
    return lambda _tool, key: values.get(key)


def test_registered_with_confirmation_capabilities_and_optional_credentials():
    module = importlib.reload(send_email_module)

    assert ToolRegistry.contains("send_email")
    tool_cls = ToolRegistry.get("send_email")
    assert tool_cls is module.SendEmailTool
    spec = tool_cls(config=_config()).spec
    assert spec.requires_confirmation is True
    assert spec.required_capabilities == ["channel:send", "network:fetch"]
    assert DEFAULT_TOOL_CAPABILITIES["send_email"] == [
        Capability.CHANNEL_SEND,
        Capability.NETWORK_FETCH,
    ]
    assert TOOL_CREDENTIALS["send_email"] == ["SMTP_USERNAME", "SMTP_PASSWORD"]
    assert is_credential_optional("send_email", "SMTP_USERNAME")
    assert is_credential_optional("send_email", "SMTP_PASSWORD")


def test_smtp_starttls_sends_message():
    with (
        patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()),
        patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls,
    ):
        result = SendEmailTool(config=_config()).execute(**_GOOD)

    assert result.success is True, result.content
    server = smtp_cls.return_value.__enter__.return_value
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("me@example.com", "app-password")
    message = server.send_message.call_args.args[0]
    assert message["To"] == "alice@example.com"
    assert message["From"] == "me@example.com"
    assert message["Subject"] == "Hello"


def test_smtp_ssl_uses_smtp_ssl():
    with (
        patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()),
        patch(f"{_MODULE}.smtplib.SMTP_SSL") as smtp_ssl_cls,
        patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls,
    ):
        result = SendEmailTool(
            config=_config(smtp_port=465, smtp_security="ssl")
        ).execute(**_GOOD)

    assert result.success is True, result.content
    smtp_cls.assert_not_called()
    server = smtp_ssl_cls.return_value.__enter__.return_value
    server.login.assert_called_once_with("me@example.com", "app-password")
    server.send_message.assert_called_once()


def test_smtp_without_encryption_never_sends_credentials():
    with (
        patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()),
        patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls,
    ):
        result = SendEmailTool(
            config=_config(smtp_host="localhost", smtp_port=25, smtp_security="none")
        ).execute(**_GOOD)

    assert result.success is True, result.content
    server = smtp_cls.return_value.__enter__.return_value
    server.login.assert_not_called()
    server.starttls.assert_not_called()
    server.send_message.assert_called_once()


def test_missing_smtp_credentials_fails_without_connecting():
    with (
        patch(f"{_MODULE}.get_tool_credential", return_value=None),
        patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls,
    ):
        result = SendEmailTool(config=_config()).execute(**_GOOD)

    assert result.success is False
    assert "No SMTP credentials" in result.content
    smtp_cls.assert_not_called()


def test_missing_smtp_host_fails():
    with patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls:
        result = SendEmailTool(config=_config(smtp_host="")).execute(**_GOOD)

    assert result.success is False
    assert "smtp_host" in result.content
    smtp_cls.assert_not_called()


def test_auth_error_does_not_leak_password():
    with (
        patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()),
        patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls,
    ):
        server = smtp_cls.return_value.__enter__.return_value
        server.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"bad credentials app-password"
        )
        result = SendEmailTool(config=_config()).execute(**_GOOD)

    assert result.success is False
    assert "rejected the username or password" in result.content
    assert "app-password" not in result.content


def test_unexpected_error_does_not_leak_message():
    with (
        patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()),
        patch(f"{_MODULE}.smtplib.SMTP", side_effect=OSError("secret-host-detail")),
    ):
        result = SendEmailTool(config=_config()).execute(**_GOOD)

    assert result.success is False
    assert "secret-host-detail" not in result.content


@pytest.mark.parametrize(
    "to",
    [
        ["Alice <alice@example.com>"],
        ["alice@example.com, bob@example.com"],
        ["not-an-address"],
        ["alice@example.com\nBcc: evil@example.com"],
        [],
        [5],
        "",
    ],
    ids=[
        "display-name",
        "comma-list",
        "no-at-sign",
        "header-injection",
        "empty-list",
        "non-string",
        "empty-string",
    ],
)
def test_invalid_recipients_rejected_without_connecting(to):
    with (
        patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()),
        patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls,
    ):
        result = SendEmailTool(config=_config()).execute(
            to=to, subject="Hello", body="Hi."
        )

    assert result.success is False
    smtp_cls.assert_not_called()


def test_too_many_recipients_rejected():
    with patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls:
        result = SendEmailTool(config=_config(max_recipients=2)).execute(
            to=["a@example.com", "b@example.com", "c@example.com"],
            subject="Hello",
            body="Hi.",
        )

    assert result.success is False
    assert "at most 2" in result.content
    smtp_cls.assert_not_called()


@pytest.mark.parametrize(
    ("subject", "body", "expected"),
    [
        ("Hello\r\nBcc: evil@example.com", "Hi.", "single line"),
        ("", "Hi.", "subject is required"),
        ("x" * 201, "Hi.", "at most 200"),
        ("Hello", "", "body is required"),
        ("Hello", "x" * 50_001, "at most 50000"),
    ],
    ids=[
        "subject-header-injection",
        "empty-subject",
        "long-subject",
        "empty-body",
        "long-body",
    ],
)
def test_invalid_subject_or_body_rejected(subject, body, expected):
    with patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls:
        result = SendEmailTool(config=_config()).execute(
            to=["alice@example.com"], subject=subject, body=body
        )

    assert result.success is False
    assert expected in result.content
    smtp_cls.assert_not_called()


def test_duplicate_recipients_are_sent_once():
    with (
        patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()),
        patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls,
    ):
        result = SendEmailTool(config=_config()).execute(
            to=["alice@example.com", "ALICE@example.com"],
            subject="Hello",
            body="Hi.",
        )

    assert result.success is True, result.content
    server = smtp_cls.return_value.__enter__.return_value
    message = server.send_message.call_args.args[0]
    assert message["To"] == "alice@example.com"


def test_unknown_backend_rejected():
    result = SendEmailTool(config=_config(backend="carrier-pigeon")).execute(**_GOOD)

    assert result.success is False
    assert "backend" in result.content


def test_gmail_sends_via_call_with_refresh():
    with (
        patch.object(
            SendEmailTool, "_gmail_credentials_path", return_value="google.json"
        ),
        patch(
            "openjarvis.connectors.google_auth.call_with_refresh",
            return_value={"id": "msg-1"},
        ) as call,
    ):
        result = SendEmailTool(config=_config(backend="gmail")).execute(**_GOOD)

    assert result.success is True, result.content
    assert result.metadata["message_id"] == "msg-1"
    api_fn, credentials_path, raw_message = call.call_args.args
    assert api_fn is send_email_module._gmail_api_send_message
    assert credentials_path == "google.json"
    decoded = base64.urlsafe_b64decode(raw_message).decode("utf-8")
    assert "To: alice@example.com" in decoded
    assert "Subject: Hello" in decoded


def test_gmail_not_connected_fails():
    with patch.object(SendEmailTool, "_gmail_credentials_path", return_value=None):
        result = SendEmailTool(config=_config(backend="gmail")).execute(**_GOOD)

    assert result.success is False
    assert "not connected" in result.content


def test_gmail_forbidden_asks_to_reconnect():
    request = httpx.Request("POST", "https://gmail.googleapis.com/send")
    response = httpx.Response(403, request=request)
    error = httpx.HTTPStatusError("forbidden", request=request, response=response)
    with (
        patch.object(
            SendEmailTool, "_gmail_credentials_path", return_value="google.json"
        ),
        patch("openjarvis.connectors.google_auth.call_with_refresh", side_effect=error),
    ):
        result = SendEmailTool(config=_config(backend="gmail")).execute(**_GOOD)

    assert result.success is False
    assert "Reconnect" in result.content


@pytest.mark.parametrize("confirmed", [False, None])
def test_executor_blocks_send_without_approval(confirmed):
    tool = SendEmailTool(config=_config())
    if confirmed is None:
        executor = ToolExecutor([tool], interactive=False)
    else:
        executor = ToolExecutor(
            [tool], interactive=True, confirm_callback=lambda _prompt: confirmed
        )

    with (
        patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()),
        patch(f"{_MODULE}.smtplib.SMTP") as smtp_cls,
    ):
        result = executor.execute(
            ToolCall(id="mail", name="send_email", arguments=json.dumps(_GOOD))
        )

    assert result.success is False
    smtp_cls.assert_not_called()


def test_spec_reports_smtp_configuration_state():
    with patch(f"{_MODULE}.get_tool_credential", side_effect=_credentials()):
        configured = SendEmailTool(config=_config()).spec.metadata
    with patch(f"{_MODULE}.get_tool_credential", return_value=None):
        unconfigured = SendEmailTool(config=_config()).spec.metadata

    assert configured["credentials_configured"] is True
    assert unconfigured["credentials_configured"] is False
