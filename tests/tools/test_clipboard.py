"""Tests for the clipboard tool."""

from __future__ import annotations

import importlib
import json
from unittest.mock import MagicMock, patch

import pytest

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolCall
from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES, Capability
from openjarvis.tools import clipboard as clipboard_module
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.clipboard import ClipboardTool

_LOADER = "openjarvis.tools.clipboard._load_clipboard"


def test_registered_as_admin_and_always_confirms():
    module = importlib.reload(clipboard_module)

    assert ToolRegistry.contains("clipboard")
    tool_cls = ToolRegistry.get("clipboard")
    assert tool_cls is module.ClipboardTool
    spec = tool_cls().spec
    assert spec.requires_confirmation is True
    assert spec.required_capabilities == ["system:admin"]
    assert DEFAULT_TOOL_CAPABILITIES["clipboard"] == [Capability.SYSTEM_ADMIN]
    assert spec.parameters["required"] == ["mode"]


def test_read_returns_clipboard_text():
    backend = MagicMock()
    backend.paste.return_value = "copied text"
    with patch(_LOADER, return_value=backend):
        result = ClipboardTool().execute(mode="read")

    assert result.success is True
    assert result.content == "copied text"
    assert result.metadata["truncated"] is False
    backend.copy.assert_not_called()


def test_write_copies_text():
    backend = MagicMock()
    with patch(_LOADER, return_value=backend):
        result = ClipboardTool().execute(mode="write", text="hello")

    assert result.success is True
    backend.copy.assert_called_once_with("hello")
    assert "5 characters" in result.content


def test_write_allows_empty_text_to_clear_clipboard():
    backend = MagicMock()
    with patch(_LOADER, return_value=backend):
        result = ClipboardTool().execute(mode="write", text="")

    assert result.success is True
    backend.copy.assert_called_once_with("")


def test_read_truncates_oversized_clipboard():
    backend = MagicMock()
    backend.paste.return_value = "x" * 100_005
    with patch(_LOADER, return_value=backend):
        result = ClipboardTool().execute(mode="read")

    assert result.success is True
    assert len(result.content) == 100_000
    assert result.metadata["truncated"] is True


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, "mode"),
        ({"mode": "delete"}, "mode"),
        ({"mode": "write"}, "text is required"),
        ({"mode": "write", "text": 5}, "text is required"),
        ({"mode": "write", "text": "x" * 100_001}, "at most"),
        ({"mode": "read", "text": "x"}, "only allowed"),
    ],
)
def test_invalid_params_rejected_without_touching_clipboard(params, expected):
    backend = MagicMock()
    with patch(_LOADER, return_value=backend) as loader:
        result = ClipboardTool().execute(**params)

    assert result.success is False
    assert expected in result.content
    loader.assert_not_called()


def test_missing_pyperclip_returns_install_hint():
    with patch(_LOADER, side_effect=ImportError("No module named 'pyperclip'")):
        result = ClipboardTool().execute(mode="read")

    assert result.success is False
    assert "pyperclip" in result.content


def test_backend_error_does_not_leak_exception_message():
    backend = MagicMock()
    backend.paste.side_effect = RuntimeError("secret token abc123")
    with patch(_LOADER, return_value=backend):
        result = ClipboardTool().execute(mode="read")

    assert result.success is False
    assert "abc123" not in result.content


@pytest.mark.parametrize("confirmed", [False, None])
def test_executor_blocks_clipboard_without_approval(confirmed):
    backend = MagicMock()
    backend.paste.return_value = "password123"
    if confirmed is None:
        executor = ToolExecutor([ClipboardTool()], interactive=False)
    else:
        executor = ToolExecutor(
            [ClipboardTool()],
            interactive=True,
            confirm_callback=lambda _prompt: confirmed,
        )

    with patch(_LOADER, return_value=backend) as loader:
        result = executor.execute(
            ToolCall(
                id="clip", name="clipboard", arguments=json.dumps({"mode": "read"})
            )
        )

    assert result.success is False
    assert "password123" not in result.content
    loader.assert_not_called()
