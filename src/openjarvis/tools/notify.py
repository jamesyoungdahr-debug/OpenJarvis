"""Desktop notification tool backed by plyer."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_TOOL_NAME = "notify"
_APP_NAME = "OpenJarvis"
_MAX_TITLE_LENGTH = 64
_MAX_MESSAGE_LENGTH = 256
_MIN_TIMEOUT_SECONDS = 1
_MAX_TIMEOUT_SECONDS = 60
_DEFAULT_TIMEOUT_SECONDS = 10


def _load_notifier() -> Any:
    from plyer import notification

    return notification


def _has_control_chars(value: str, *, allow_newlines: bool = False) -> bool:
    for char in value:
        if allow_newlines and char in "\n\t":
            continue
        if ord(char) < 32 or ord(char) == 127:
            return True
    return False


@ToolRegistry.register("notify")
class NotifyTool(BaseTool):
    """Show a desktop notification on the machine running OpenJarvis."""

    tool_id = _TOOL_NAME
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=_TOOL_NAME,
            description=(
                "Show a desktop notification on the computer running OpenJarvis. "
                "Use it to alert the user when a long task finishes or needs "
                "their attention."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "maxLength": _MAX_TITLE_LENGTH,
                        "description": "Short notification title.",
                    },
                    "message": {
                        "type": "string",
                        "maxLength": _MAX_MESSAGE_LENGTH,
                        "description": "Notification body text.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": _MIN_TIMEOUT_SECONDS,
                        "maximum": _MAX_TIMEOUT_SECONDS,
                        "description": (
                            "How long the notification stays visible, in seconds. "
                            "Defaults to 10."
                        ),
                    },
                },
                "required": ["title", "message"],
                "additionalProperties": False,
            },
            category="system",
            latency_estimate=0.5,
            timeout_seconds=15.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        title_value = params.get("title")
        if not isinstance(title_value, str) or not title_value.strip():
            return self._failure("A notification title is required.")
        message_value = params.get("message")
        if not isinstance(message_value, str) or not message_value.strip():
            return self._failure("A notification message is required.")

        title = title_value.strip()
        message = message_value.strip()
        if len(title) > _MAX_TITLE_LENGTH:
            return self._failure(
                f"The title must be at most {_MAX_TITLE_LENGTH} characters."
            )
        if len(message) > _MAX_MESSAGE_LENGTH:
            return self._failure(
                f"The message must be at most {_MAX_MESSAGE_LENGTH} characters."
            )
        if _has_control_chars(title):
            return self._failure("The title must not contain control characters.")
        if _has_control_chars(message, allow_newlines=True):
            return self._failure("The message must not contain control characters.")

        timeout = params.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int)
            or not _MIN_TIMEOUT_SECONDS <= timeout <= _MAX_TIMEOUT_SECONDS
        ):
            return self._failure(
                f"timeout_seconds must be an integer from {_MIN_TIMEOUT_SECONDS} "
                f"to {_MAX_TIMEOUT_SECONDS}."
            )

        try:
            notifier = _load_notifier()
        except ImportError:
            return self._failure(
                "Desktop notifications need the plyer package. Install it with: "
                "pip install 'openjarvis[notify]'"
            )

        try:
            notifier.notify(
                title=title,
                message=message,
                app_name=_APP_NAME,
                timeout=timeout,
            )
        except NotImplementedError:
            return self._failure(
                "Desktop notifications are not supported on this platform."
            )
        except Exception as exc:
            return self._failure(
                f"Could not show the notification ({type(exc).__name__})."
            )

        return ToolResult(
            tool_name=_TOOL_NAME,
            content=f"Notification shown: {title}",
            success=True,
            metadata={"timeout_seconds": timeout},
        )

    @staticmethod
    def _failure(message: str) -> ToolResult:
        return ToolResult(tool_name=_TOOL_NAME, content=message, success=False)


__all__ = ["NotifyTool"]
