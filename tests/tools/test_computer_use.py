"""Tests for the computer_use desktop control tool."""

from __future__ import annotations

import importlib
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolCall
from openjarvis.security.approval_callback import (
    NEVER_REMEMBER_TOOLS,
    make_audited_auto_approve_callback,
)
from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES, Capability
from openjarvis.tools import computer_use as computer_use_module
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.computer_use import ComputerUseTool

_LOADER = "openjarvis.tools.computer_use._load_pyautogui"


class FailSafeException(Exception):
    pass


def _gui():
    gui = MagicMock()
    gui.KEYBOARD_KEYS = ["enter", "ctrl", "c", "alt", "tab", "f5", "shift"]
    gui.size.return_value = (1920, 1080)
    return gui


def test_registered_as_admin_confirming_and_never_remembered():
    module = importlib.reload(computer_use_module)

    assert ToolRegistry.contains("computer_use")
    tool_cls = ToolRegistry.get("computer_use")
    assert tool_cls is module.ComputerUseTool
    spec = tool_cls().spec
    assert spec.requires_confirmation is True
    assert spec.required_capabilities == ["system:admin"]
    assert DEFAULT_TOOL_CAPABILITIES["computer_use"] == [Capability.SYSTEM_ADMIN]
    assert "computer_use" in NEVER_REMEMBER_TOOLS


def test_audited_auto_approve_refuses_computer_use():
    confirm = make_audited_auto_approve_callback(store=MagicMock())

    assert confirm("Allow execution of tool 'computer_use' with args {}?") is False


def test_move():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="move", x=100, y=200)

    assert result.success is True, result.content
    gui.moveTo.assert_called_once_with(
        100, 200, duration=computer_use_module._MOVE_DURATION_SECONDS
    )


def test_click_at_point_with_button():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="click", x=5, y=6, button="right")

    assert result.success is True, result.content
    gui.click.assert_called_once_with(x=5, y=6, button="right")


def test_click_without_point_uses_current_position_and_left_button():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="click")

    assert result.success is True, result.content
    gui.click.assert_called_once_with(x=None, y=None, button="left")
    gui.size.assert_not_called()


def test_double_click():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="double_click", x=1, y=2)

    assert result.success is True, result.content
    gui.doubleClick.assert_called_once_with(x=1, y=2, button="left")


def test_type_does_not_echo_text():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="type", text="hunter2\n")

    assert result.success is True, result.content
    gui.write.assert_called_once_with(
        "hunter2\n", interval=computer_use_module._TYPE_INTERVAL_SECONDS
    )
    assert "hunter2" not in result.content


def test_press_normalizes_key_name():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="press", key=" Enter ")

    assert result.success is True, result.content
    gui.press.assert_called_once_with("enter")


def test_hotkey():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="hotkey", keys=["Ctrl", "c"])

    assert result.success is True, result.content
    gui.hotkey.assert_called_once_with("ctrl", "c")


def test_scroll_at_point():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="scroll", clicks=-5, x=10, y=20)

    assert result.success is True, result.content
    gui.scroll.assert_called_once_with(-5, x=10, y=20)


def test_screenshot_saves_file_and_returns_only_the_path():
    gui = _gui()
    image = MagicMock()
    image.size = (1920, 1080)
    gui.screenshot.return_value = image
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="screenshot")

    try:
        assert result.success is True, result.content
        path = result.metadata["path"]
        assert path.endswith(".png")
        image.save.assert_called_once_with(path)
        assert path in result.content
        assert set(result.metadata) == {"action", "path", "width", "height"}
    finally:
        if os.path.exists(result.metadata.get("path", "")):
            os.remove(result.metadata["path"])


def test_failed_screenshot_removes_temp_file(tmp_path):
    shot = tmp_path / "shot.png"
    fd = os.open(shot, os.O_CREAT | os.O_WRONLY)
    gui = _gui()
    gui.screenshot.return_value.save.side_effect = OSError("disk full")
    with (
        patch(_LOADER, return_value=gui),
        patch(
            "openjarvis.tools.computer_use.tempfile.mkstemp",
            return_value=(fd, str(shot)),
        ),
    ):
        result = ComputerUseTool().execute(action="screenshot")

    assert result.success is False
    assert not shot.exists()


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, "action must be one of"),
        ({"action": "drag"}, "action must be one of"),
        ({"action": "move", "x": 1}, "given together"),
        ({"action": "move"}, "x and y are required"),
        ({"action": "move", "x": -1, "y": 2}, "non-negative"),
        ({"action": "move", "x": True, "y": 2}, "non-negative"),
        ({"action": "click", "button": "back"}, "left, right, or middle"),
        ({"action": "type", "text": ""}, "text is required"),
        ({"action": "type", "text": "h\u00e9llo"}, "printable ASCII"),
        ({"action": "type", "text": "a\x1b[2J"}, "printable ASCII"),
        ({"action": "type", "text": "x" * 1001}, "at most 1000"),
        ({"action": "press"}, "key is required"),
        ({"action": "hotkey", "keys": ["ctrl"]}, "2 to 4"),
        ({"action": "hotkey", "keys": ["a", "b", "c", "d", "e"]}, "2 to 4"),
        ({"action": "scroll", "clicks": 0}, "non-zero"),
        ({"action": "scroll", "clicks": 51}, "non-zero"),
        ({"action": "screenshot", "x": 1, "y": 1}, "does not accept"),
        ({"action": "type", "text": "hi", "key": "enter"}, "does not accept"),
    ],
    ids=[
        "missing-action",
        "unknown-action",
        "x-without-y",
        "move-without-point",
        "negative-x",
        "bool-x",
        "bad-button",
        "empty-text",
        "non-ascii-text",
        "escape-sequence-text",
        "long-text",
        "missing-key",
        "one-hotkey-key",
        "five-hotkey-keys",
        "zero-scroll",
        "large-scroll",
        "screenshot-with-point",
        "type-with-key",
    ],
)
def test_invalid_params_rejected_before_loading_pyautogui(params, expected):
    with patch(_LOADER) as loader:
        result = ComputerUseTool().execute(**params)

    assert result.success is False
    assert expected in result.content
    loader.assert_not_called()


def test_unknown_key_name_rejected_without_pressing():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="press", key="notakey")

    assert result.success is False
    assert "Unknown key name" in result.content
    gui.press.assert_not_called()


def test_point_outside_screen_rejected_without_moving():
    gui = _gui()
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="move", x=1920, y=10)

    assert result.success is False
    assert "outside the 1920x1080 screen" in result.content
    gui.moveTo.assert_not_called()


def test_missing_pyautogui_returns_install_hint():
    with patch(_LOADER, side_effect=ImportError("No module named 'pyautogui'")):
        result = ComputerUseTool().execute(action="screenshot")

    assert result.success is False
    assert "pyautogui" in result.content


def test_no_desktop_session_fails_cleanly():
    with patch(_LOADER, side_effect=KeyError("DISPLAY")):
        result = ComputerUseTool().execute(action="screenshot")

    assert result.success is False
    assert "No desktop session" in result.content


def test_fail_safe_is_reported():
    gui = _gui()
    gui.moveTo.side_effect = FailSafeException("corner")
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="move", x=0, y=0)

    assert result.success is False
    assert "fail-safe" in result.content


def test_backend_error_does_not_leak_message():
    gui = _gui()
    gui.write.side_effect = RuntimeError("secret window title")
    with patch(_LOADER, return_value=gui):
        result = ComputerUseTool().execute(action="type", text="hi")

    assert result.success is False
    assert "secret window title" not in result.content


@pytest.mark.parametrize("confirmed", [False, None], ids=["denied", "non-interactive"])
def test_executor_blocks_computer_use_without_approval(confirmed):
    if confirmed is None:
        executor = ToolExecutor([ComputerUseTool()], interactive=False)
    else:
        executor = ToolExecutor(
            [ComputerUseTool()],
            interactive=True,
            confirm_callback=lambda _prompt: confirmed,
        )

    with patch(_LOADER) as loader:
        result = executor.execute(
            ToolCall(
                id="cu",
                name="computer_use",
                arguments=json.dumps({"action": "type", "text": "rm -rf /"}),
            )
        )

    assert result.success is False
    loader.assert_not_called()
