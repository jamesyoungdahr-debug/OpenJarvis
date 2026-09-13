"""Clipboard tool backed by pyperclip."""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_TOOL_NAME = "clipboard"
_VALID_MODES = frozenset({"read", "write"})
_MAX_TEXT_LENGTH = 100_000


def _load_clipboard() -> Any:
    import pyperclip

    return pyperclip


@ToolRegistry.register("clipboard")
class ClipboardTool(BaseTool):
    """Read text from, or write text to, the system clipboard."""

    tool_id = _TOOL_NAME
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=_TOOL_NAME,
            description=(
                "Read the text currently on the system clipboard, or replace it "
                "with new text. Every call needs the user's approval, because the "
                "clipboard often holds passwords and other private data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": sorted(_VALID_MODES),
                        "description": (
                            "'read' returns the clipboard text; 'write' replaces "
                            "it with text."
                        ),
                    },
                    "text": {
                        "type": "string",
                        "maxLength": _MAX_TEXT_LENGTH,
                        "description": (
                            "Text to put on the clipboard. Required when mode is "
                            "'write'; not allowed when mode is 'read'."
                        ),
                    },
                },
                "required": ["mode"],
                "additionalProperties": False,
            },
            category="system",
            latency_estimate=0.2,
            timeout_seconds=10.0,
            requires_confirmation=True,
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        mode = params.get("mode")
        if not isinstance(mode, str) or mode not in _VALID_MODES:
            return self._failure("mode must be 'read' or 'write'.")

        text = params.get("text")
        if mode == "write":
            if not isinstance(text, str):
                return self._failure("text is required when mode is 'write'.")
            if len(text) > _MAX_TEXT_LENGTH:
                return self._failure(
                    f"text must be at most {_MAX_TEXT_LENGTH} characters."
                )
        elif text is not None:
            return self._failure("text is only allowed when mode is 'write'.")

        try:
            clipboard = _load_clipboard()
        except ImportError:
            return self._failure(
                "Clipboard access needs the pyperclip package. Install it with: "
                "pip install 'openjarvis[clipboard]'"
            )

        try:
            if mode == "write":
                clipboard.copy(text)
                content = ""
            else:
                content = clipboard.paste()
        except Exception as exc:
            return self._failure(
                f"Clipboard access failed ({type(exc).__name__}). On Linux, "
                "install xclip or xsel."
            )

        if mode == "write":
            return ToolResult(
                tool_name=_TOOL_NAME,
                content=f"Copied {len(text)} characters to the clipboard.",
                success=True,
                metadata={"mode": "write", "length": len(text)},
            )

        if not isinstance(content, str):
            content = ""
        truncated = len(content) > _MAX_TEXT_LENGTH
        if truncated:
            content = content[:_MAX_TEXT_LENGTH]
        return ToolResult(
            tool_name=_TOOL_NAME,
            content=content,
            success=True,
            metadata={"mode": "read", "length": len(content), "truncated": truncated},
        )

    @staticmethod
    def _failure(message: str) -> ToolResult:
        return ToolResult(tool_name=_TOOL_NAME, content=message, success=False)


__all__ = ["ClipboardTool"]
