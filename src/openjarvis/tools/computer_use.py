"""Desktop pointer, keyboard, and screenshot control via pyautogui."""

from __future__ import annotations

import contextlib
import os
import tempfile
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_TOOL_NAME = "computer_use"
_ACTION_PARAMS: dict[str, frozenset[str]] = {
    "screenshot": frozenset(),
    "move": frozenset({"x", "y"}),
    "click": frozenset({"x", "y", "button"}),
    "double_click": frozenset({"x", "y", "button"}),
    "type": frozenset({"text"}),
    "press": frozenset({"key"}),
    "hotkey": frozenset({"keys"}),
    "scroll": frozenset({"clicks", "x", "y"}),
}
_VALID_BUTTONS = ("left", "right", "middle")
_MAX_TEXT_LENGTH = 1000
_MAX_HOTKEY_KEYS = 4
_MAX_SCROLL_CLICKS = 50
_MAX_KEY_NAME_LENGTH = 30
_MOVE_DURATION_SECONDS = 0.2
_TYPE_INTERVAL_SECONDS = 0.01


def _load_pyautogui() -> Any:
    import pyautogui

    # Keep the fail-safe on: moving the pointer into a screen corner aborts.
    pyautogui.FAILSAFE = True
    return pyautogui


def _parse_point(
    params: dict[str, Any], *, required: bool
) -> tuple[tuple[int, int] | None, str | None]:
    has_x = "x" in params
    has_y = "y" in params
    if not has_x and not has_y:
        return None, ("x and y are required." if required else None)
    if has_x != has_y:
        return None, "x and y must be given together."
    x, y = params["x"], params["y"]
    for value in (x, y):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None, "x and y must be non-negative integers."
    return (x, y), None


def _is_typeable(text: str) -> bool:
    return all(32 <= ord(char) < 127 or char in "\n\t" for char in text)


@ToolRegistry.register("computer_use")
class ComputerUseTool(BaseTool):
    """Control the desktop pointer and keyboard, or take a screenshot."""

    tool_id = _TOOL_NAME
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=_TOOL_NAME,
            description=(
                "Control this computer's desktop: take a screenshot (saved to a "
                "file), move the pointer, click, double-click, scroll, type text, "
                "press a key, or press a key combination. Every call needs the "
                "user's approval. Screenshots are saved to disk, not returned as "
                "images."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(_ACTION_PARAMS),
                        "description": "The desktop action to perform.",
                    },
                    "x": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Screen x coordinate in pixels. Required for move; "
                            "optional (with y) for click, double_click, and scroll."
                        ),
                    },
                    "y": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Screen y coordinate in pixels. Required for move; "
                            "optional (with x) for click, double_click, and scroll."
                        ),
                    },
                    "button": {
                        "type": "string",
                        "enum": list(_VALID_BUTTONS),
                        "description": (
                            "Mouse button for click and double_click. Defaults to left."
                        ),
                    },
                    "text": {
                        "type": "string",
                        "maxLength": _MAX_TEXT_LENGTH,
                        "description": (
                            "Text to type (type action). Printable ASCII, "
                            "newlines, and tabs only."
                        ),
                    },
                    "key": {
                        "type": "string",
                        "description": (
                            "Key to press, such as 'enter' or 'f5' (press action)."
                        ),
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": _MAX_HOTKEY_KEYS,
                        "description": (
                            "Keys pressed together, such as ['ctrl', 'c'] (hotkey "
                            "action)."
                        ),
                    },
                    "clicks": {
                        "type": "integer",
                        "minimum": -_MAX_SCROLL_CLICKS,
                        "maximum": _MAX_SCROLL_CLICKS,
                        "description": (
                            "Scroll amount (scroll action). Positive scrolls up, "
                            "negative scrolls down."
                        ),
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            category="system",
            latency_estimate=1.0,
            timeout_seconds=60.0,
            requires_confirmation=True,
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action")
        if not isinstance(action, str) or action not in _ACTION_PARAMS:
            return self._failure(f"action must be one of: {', '.join(_ACTION_PARAMS)}.")
        unexpected = sorted(set(params) - {"action"} - _ACTION_PARAMS[action])
        if unexpected:
            return self._failure(f"{action} does not accept: {', '.join(unexpected)}.")

        point, error = _parse_point(params, required=action == "move")
        if error:
            return self._failure(error)

        button = params.get("button", "left")
        if action in {"click", "double_click"} and button not in _VALID_BUTTONS:
            return self._failure("button must be left, right, or middle.")

        text = ""
        if action == "type":
            text = params.get("text")
            if not isinstance(text, str) or not text:
                return self._failure("text is required.")
            if len(text) > _MAX_TEXT_LENGTH:
                return self._failure(
                    f"text must be at most {_MAX_TEXT_LENGTH} characters."
                )
            if not _is_typeable(text):
                return self._failure(
                    "text may only contain printable ASCII characters, newlines, "
                    "and tabs."
                )

        keys: list[str] = []
        if action == "press":
            key = params.get("key")
            if not isinstance(key, str) or not key.strip():
                return self._failure("key is required.")
            keys = [key.strip().lower()]
        elif action == "hotkey":
            raw_keys = params.get("keys")
            if (
                not isinstance(raw_keys, list)
                or not 2 <= len(raw_keys) <= _MAX_HOTKEY_KEYS
                or not all(isinstance(k, str) and k.strip() for k in raw_keys)
            ):
                return self._failure(
                    f"keys must list 2 to {_MAX_HOTKEY_KEYS} key names."
                )
            keys = [k.strip().lower() for k in raw_keys]

        clicks = 0
        if action == "scroll":
            clicks = params.get("clicks")
            if (
                isinstance(clicks, bool)
                or not isinstance(clicks, int)
                or clicks == 0
                or abs(clicks) > _MAX_SCROLL_CLICKS
            ):
                return self._failure(
                    f"clicks must be a non-zero integer from -{_MAX_SCROLL_CLICKS} "
                    f"to {_MAX_SCROLL_CLICKS}."
                )

        try:
            gui = _load_pyautogui()
        except ImportError:
            return self._failure(
                "Computer use needs the pyautogui package. Install it with: "
                "pip install 'openjarvis[computer-use]'"
            )
        except Exception as exc:
            return self._failure(
                f"No desktop session is available ({type(exc).__name__})."
            )

        if keys:
            valid_keys = set(getattr(gui, "KEYBOARD_KEYS", ()))
            unknown = [k[:_MAX_KEY_NAME_LENGTH] for k in keys if k not in valid_keys]
            if unknown:
                return self._failure(f"Unknown key name: {', '.join(unknown)}.")

        if point is not None:
            try:
                width, height = gui.size()
            except Exception as exc:
                return self._failure(
                    f"Could not read the screen size ({type(exc).__name__})."
                )
            if point[0] >= width or point[1] >= height:
                return self._failure(
                    f"({point[0]}, {point[1]}) is outside the {width}x{height} screen."
                )

        try:
            return self._perform(gui, action, point, button, text, keys, clicks)
        except Exception as exc:
            if type(exc).__name__ == "FailSafeException":
                return self._failure(
                    "Stopped by the pyautogui fail-safe: the pointer is in a "
                    "screen corner."
                )
            return self._failure(f"The {action} action failed ({type(exc).__name__}).")

    def _perform(
        self,
        gui: Any,
        action: str,
        point: tuple[int, int] | None,
        button: str,
        text: str,
        keys: list[str],
        clicks: int,
    ) -> ToolResult:
        x, y = point if point is not None else (None, None)
        where = f" at ({x}, {y})" if point is not None else ""
        if action == "screenshot":
            return self._screenshot(gui)
        if action == "move":
            gui.moveTo(x, y, duration=_MOVE_DURATION_SECONDS)
            return self._success(action, f"Moved the pointer to ({x}, {y}).")
        if action == "click":
            gui.click(x=x, y=y, button=button)
            return self._success(action, f"Clicked the {button} button{where}.")
        if action == "double_click":
            gui.doubleClick(x=x, y=y, button=button)
            return self._success(action, f"Double-clicked the {button} button{where}.")
        if action == "type":
            gui.write(text, interval=_TYPE_INTERVAL_SECONDS)
            # The approval prompt already showed the text; do not echo it back.
            return self._success(action, f"Typed {len(text)} characters.")
        if action == "press":
            gui.press(keys[0])
            return self._success(action, f"Pressed {keys[0]}.")
        if action == "hotkey":
            gui.hotkey(*keys)
            return self._success(action, f"Pressed {'+'.join(keys)}.")
        gui.scroll(clicks, x=x, y=y)
        return self._success(action, f"Scrolled {clicks} clicks{where}.")

    @staticmethod
    def _screenshot(gui: Any) -> ToolResult:
        # Save to a file and return only the path: tool metadata is persisted to
        # traces, so embedding the image would store screen contents there.
        fd, path = tempfile.mkstemp(prefix="openjarvis_screen_", suffix=".png")
        os.close(fd)
        try:
            image = gui.screenshot()
            image.save(path)
            width, height = image.size
        except Exception:
            with contextlib.suppress(OSError):
                os.remove(path)
            raise
        return ToolResult(
            tool_name=_TOOL_NAME,
            content=f"Saved a {width}x{height} screenshot to {path}.",
            success=True,
            metadata={
                "action": "screenshot",
                "path": path,
                "width": width,
                "height": height,
            },
        )

    @staticmethod
    def _success(action: str, message: str) -> ToolResult:
        return ToolResult(
            tool_name=_TOOL_NAME,
            content=message,
            success=True,
            metadata={"action": action},
        )

    @staticmethod
    def _failure(message: str) -> ToolResult:
        return ToolResult(tool_name=_TOOL_NAME, content=message, success=False)


__all__ = ["ComputerUseTool"]
