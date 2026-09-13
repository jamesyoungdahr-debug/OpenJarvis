"""Tests for the desktop notification tool."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest

from openjarvis.core.registry import ToolRegistry
from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES
from openjarvis.tools import notify as notify_module
from openjarvis.tools.notify import NotifyTool

_LOADER = "openjarvis.tools.notify._load_notifier"


def test_registered_with_no_capabilities_and_no_confirmation():
    module = importlib.reload(notify_module)

    assert ToolRegistry.contains("notify")
    tool_cls = ToolRegistry.get("notify")
    assert tool_cls is module.NotifyTool
    spec = tool_cls().spec
    assert spec.requires_confirmation is False
    assert spec.required_capabilities == []
    assert DEFAULT_TOOL_CAPABILITIES["notify"] == []
    assert spec.parameters["required"] == ["title", "message"]


def test_execute_shows_notification():
    notifier = MagicMock()
    with patch(_LOADER, return_value=notifier):
        result = NotifyTool().execute(
            title="Build done", message="All tests passed.", timeout_seconds=5
        )

    assert result.success is True
    notifier.notify.assert_called_once_with(
        title="Build done",
        message="All tests passed.",
        app_name="OpenJarvis",
        timeout=5,
    )


def test_default_timeout_is_ten_seconds():
    notifier = MagicMock()
    with patch(_LOADER, return_value=notifier):
        result = NotifyTool().execute(title="T", message="M")

    assert result.success is True
    assert notifier.notify.call_args.kwargs["timeout"] == 10


def test_missing_plyer_returns_install_hint():
    with patch(_LOADER, side_effect=ImportError("No module named 'plyer'")):
        result = NotifyTool().execute(title="T", message="M")

    assert result.success is False
    assert "plyer" in result.content


def test_unsupported_platform_fails_cleanly():
    notifier = MagicMock()
    notifier.notify.side_effect = NotImplementedError()
    with patch(_LOADER, return_value=notifier):
        result = NotifyTool().execute(title="T", message="M")

    assert result.success is False
    assert "not supported" in result.content


def test_backend_error_does_not_leak_exception_message():
    notifier = MagicMock()
    notifier.notify.side_effect = RuntimeError("secret path C:/Users/someone")
    with patch(_LOADER, return_value=notifier):
        result = NotifyTool().execute(title="T", message="M")

    assert result.success is False
    assert "secret path" not in result.content


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"message": "M"}, "title"),
        ({"title": "   ", "message": "M"}, "title"),
        ({"title": "T"}, "message"),
        ({"title": "T" * 65, "message": "M"}, "title"),
        ({"title": "T", "message": "M" * 257}, "message"),
        ({"title": "bad\x07title", "message": "M"}, "control"),
        ({"title": "T", "message": "bad\x1bmessage"}, "control"),
        ({"title": "T", "message": "M", "timeout_seconds": 0}, "timeout_seconds"),
        ({"title": "T", "message": "M", "timeout_seconds": 61}, "timeout_seconds"),
        ({"title": "T", "message": "M", "timeout_seconds": True}, "timeout_seconds"),
    ],
)
def test_invalid_params_rejected_without_notifying(params, expected):
    notifier = MagicMock()
    with patch(_LOADER, return_value=notifier):
        result = NotifyTool().execute(**params)

    assert result.success is False
    assert expected in result.content.lower()
    notifier.notify.assert_not_called()


def test_multiline_message_is_allowed():
    notifier = MagicMock()
    with patch(_LOADER, return_value=notifier):
        result = NotifyTool().execute(title="T", message="line one\nline two")

    assert result.success is True
