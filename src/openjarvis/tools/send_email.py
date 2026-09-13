"""send_email tool: send a plain-text email over SMTP or the Gmail API."""

from __future__ import annotations

import base64
import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Any

import httpx

from openjarvis.core.credentials import get_tool_credential
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_TOOL_NAME = "send_email"
_USERNAME_KEY = "SMTP_USERNAME"
_PASSWORD_KEY = "SMTP_PASSWORD"
_VALID_BACKENDS = frozenset({"smtp", "gmail"})
_VALID_SMTP_SECURITY = frozenset({"starttls", "ssl", "none"})
_DEFAULT_MAX_RECIPIENTS = 10
_HARD_MAX_RECIPIENTS = 50
_MAX_ADDRESS_LENGTH = 254
_MAX_SUBJECT_LENGTH = 200
_MAX_BODY_LENGTH = 50_000
_SMTP_TIMEOUT_SECONDS = 30.0
_GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _gmail_api_send_message(token: str, raw_message: str) -> dict[str, Any]:
    """Call Gmail ``messages.send`` with a base64url-encoded RFC 822 message."""
    response = httpx.post(
        _GMAIL_SEND_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"raw": raw_message},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def _validate_address(value: Any) -> str | None:
    """Return *value* if it is a single bare address (no display name, no list)."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > _MAX_ADDRESS_LENGTH or "@" not in candidate:
        return None
    try:
        address = Address(addr_spec=candidate)
    except Exception:
        return None
    if address.addr_spec != candidate:
        return None
    return candidate


def _has_control_chars(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _build_message(
    sender: str, recipients: list[str], subject: str, body: str
) -> EmailMessage:
    message = EmailMessage()
    if sender:
        message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    # Without an explicit domain make_msgid embeds the local hostname.
    domain = sender.rsplit("@", 1)[1] if "@" in sender else "openjarvis.local"
    message["Message-ID"] = make_msgid(domain=domain)
    message.set_content(body)
    return message


@ToolRegistry.register("send_email")
class SendEmailTool(BaseTool):
    """Send a plain-text email to one or more recipients."""

    tool_id = _TOOL_NAME
    is_local = False

    def __init__(self, *, config: Any = None) -> None:
        self._config_error = False
        if config is None:
            try:
                from openjarvis.core.config import load_config

                config = load_config().tools.send_email
            except Exception:
                self._config_error = True
                config = None
        self._backend = str(getattr(config, "backend", "smtp") or "").strip().lower()
        self._smtp_host = str(getattr(config, "smtp_host", "") or "").strip()
        port = getattr(config, "smtp_port", 587)
        self._smtp_port = (
            port if isinstance(port, int) and not isinstance(port, bool) else 0
        )
        self._smtp_security = (
            str(getattr(config, "smtp_security", "starttls") or "").strip().lower()
        )
        self._from_address = str(getattr(config, "from_address", "") or "").strip()
        max_recipients = getattr(config, "max_recipients", _DEFAULT_MAX_RECIPIENTS)
        if isinstance(max_recipients, bool) or not isinstance(max_recipients, int):
            max_recipients = _DEFAULT_MAX_RECIPIENTS
        self._max_recipients = max(1, min(max_recipients, _HARD_MAX_RECIPIENTS))

    def _smtp_credentials(self) -> tuple[str | None, str | None]:
        try:
            username = get_tool_credential(_TOOL_NAME, _USERNAME_KEY)
            password = get_tool_credential(_TOOL_NAME, _PASSWORD_KEY)
        except (AttributeError, OSError, TypeError, ValueError):
            return None, None
        return (username or None), (password or None)

    def _gmail_credentials_path(self) -> str | None:
        try:
            from openjarvis.connectors.oauth import resolve_google_credentials
            from openjarvis.core.paths import get_config_dir
        except ImportError:
            return None
        path = resolve_google_credentials(
            str(get_config_dir() / "connectors" / "gmail.json")
        )
        return path if Path(path).exists() else None

    def is_configured(self) -> bool:
        """Return whether the selected backend has what it needs to send."""
        if self._backend == "gmail":
            return self._gmail_credentials_path() is not None
        if self._backend != "smtp" or not self._smtp_host:
            return False
        if self._smtp_security == "none":
            return True
        username, password = self._smtp_credentials()
        return bool(username and password)

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=_TOOL_NAME,
            description=(
                "Send a plain-text email. Every send needs the user's approval, "
                "which shows the recipients, subject, and body."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": self._max_recipients,
                        "description": (
                            "Recipient email addresses, each a bare address such "
                            "as name@example.com."
                        ),
                    },
                    "subject": {
                        "type": "string",
                        "maxLength": _MAX_SUBJECT_LENGTH,
                        "description": "Single-line subject.",
                    },
                    "body": {
                        "type": "string",
                        "maxLength": _MAX_BODY_LENGTH,
                        "description": "Plain-text message body.",
                    },
                },
                "required": ["to", "subject", "body"],
                "additionalProperties": False,
            },
            category="communication",
            latency_estimate=2.0,
            timeout_seconds=45.0,
            requires_confirmation=True,
            required_capabilities=["channel:send", "network:fetch"],
            metadata={
                "backend": self._backend,
                "credentials_configured": self.is_configured(),
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._config_error:
            return self._failure("send_email configuration could not be loaded.")
        if self._backend not in _VALID_BACKENDS:
            return self._failure(
                "[tools.send_email].backend must be 'smtp' or 'gmail'."
            )

        raw_recipients = params.get("to")
        if isinstance(raw_recipients, str):
            raw_recipients = [raw_recipients]
        if not isinstance(raw_recipients, list) or not raw_recipients:
            return self._failure("to must list one or more email addresses.")
        if len(raw_recipients) > self._max_recipients:
            return self._failure(
                f"to can include at most {self._max_recipients} recipients."
            )
        recipients: list[str] = []
        seen: set[str] = set()
        for value in raw_recipients:
            address = _validate_address(value)
            if address is None:
                return self._failure(
                    "Every recipient must be a single plain email address such as "
                    "name@example.com."
                )
            if address.lower() not in seen:
                seen.add(address.lower())
                recipients.append(address)

        subject_value = params.get("subject")
        if not isinstance(subject_value, str) or not subject_value.strip():
            return self._failure("subject is required.")
        subject = subject_value.strip()
        if len(subject) > _MAX_SUBJECT_LENGTH:
            return self._failure(
                f"subject must be at most {_MAX_SUBJECT_LENGTH} characters."
            )
        if _has_control_chars(subject):
            return self._failure("subject must be a single line of text.")

        body = params.get("body")
        if not isinstance(body, str) or not body.strip():
            return self._failure("body is required.")
        if len(body) > _MAX_BODY_LENGTH:
            return self._failure(f"body must be at most {_MAX_BODY_LENGTH} characters.")

        if self._backend == "gmail":
            return self._send_gmail(recipients, subject, body)
        return self._send_smtp(recipients, subject, body)

    def _send_smtp(self, recipients: list[str], subject: str, body: str) -> ToolResult:
        if not self._smtp_host:
            return self._failure(
                "No SMTP server configured. Set [tools.send_email].smtp_host."
            )
        if not 1 <= self._smtp_port <= 65535:
            return self._failure(
                "[tools.send_email].smtp_port must be between 1 and 65535."
            )
        if self._smtp_security not in _VALID_SMTP_SECURITY:
            return self._failure(
                "[tools.send_email].smtp_security must be 'starttls', 'ssl', or 'none'."
            )

        username, password = self._smtp_credentials()
        # Credentials are never sent over an unencrypted connection: with
        # smtp_security = "none" the tool relays without logging in.
        if self._smtp_security != "none" and not (username and password):
            return self._failure(
                f"No SMTP credentials configured. Set {_USERNAME_KEY} and "
                f"{_PASSWORD_KEY} for the send_email tool."
            )
        sender = self._from_address or (username or "")
        if _validate_address(sender) is None:
            return self._failure(
                "Set [tools.send_email].from_address to a valid sender address."
            )

        message = _build_message(sender, recipients, subject, body)
        try:
            if self._smtp_security == "ssl":
                with smtplib.SMTP_SSL(
                    self._smtp_host,
                    self._smtp_port,
                    timeout=_SMTP_TIMEOUT_SECONDS,
                    context=ssl.create_default_context(),
                ) as server:
                    server.login(username, password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(
                    self._smtp_host, self._smtp_port, timeout=_SMTP_TIMEOUT_SECONDS
                ) as server:
                    if self._smtp_security == "starttls":
                        server.starttls(context=ssl.create_default_context())
                        server.login(username, password)
                    server.send_message(message)
        except smtplib.SMTPAuthenticationError:
            return self._failure("The SMTP server rejected the username or password.")
        except smtplib.SMTPRecipientsRefused:
            return self._failure("The SMTP server refused one or more recipients.")
        except Exception as exc:
            return self._failure(f"Sending the email failed ({type(exc).__name__}).")

        return self._success("smtp", recipients, subject)

    def _send_gmail(self, recipients: list[str], subject: str, body: str) -> ToolResult:
        credentials_path = self._gmail_credentials_path()
        if credentials_path is None:
            return self._failure(
                "Gmail is not connected. Connect the Google connector first."
            )
        if self._from_address and _validate_address(self._from_address) is None:
            return self._failure(
                "Set [tools.send_email].from_address to a valid sender address."
            )

        try:
            from openjarvis.connectors.google_auth import (
                GoogleAuthError,
                call_with_refresh,
            )
        except ImportError:
            return self._failure("Gmail sending is unavailable in this installation.")

        message = _build_message(self._from_address, recipients, subject, body)
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        try:
            response = call_with_refresh(
                _gmail_api_send_message, credentials_path, raw_message
            )
        except GoogleAuthError:
            return self._failure(
                "Gmail authorization failed. Reconnect the Google connector."
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 403:
                return self._failure(
                    "Gmail refused to send (HTTP 403). Reconnect the Google "
                    "connector so it is allowed to send mail."
                )
            return self._failure(f"Gmail rejected the message (HTTP {status}).")
        except Exception as exc:
            return self._failure(f"Sending the email failed ({type(exc).__name__}).")

        message_id = response.get("id", "") if isinstance(response, dict) else ""
        return self._success("gmail", recipients, subject, str(message_id))

    @staticmethod
    def _success(
        backend: str, recipients: list[str], subject: str, message_id: str = ""
    ) -> ToolResult:
        metadata: dict[str, Any] = {"backend": backend, "recipients": len(recipients)}
        if message_id:
            metadata["message_id"] = message_id
        return ToolResult(
            tool_name=_TOOL_NAME,
            content=f"Sent '{subject}' to {', '.join(recipients)}.",
            success=True,
            metadata=metadata,
        )

    @staticmethod
    def _failure(message: str) -> ToolResult:
        return ToolResult(tool_name=_TOOL_NAME, content=message, success=False)


__all__ = ["SendEmailTool"]
