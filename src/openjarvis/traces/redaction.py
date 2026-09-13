"""Redact sensitive or bulky tool data before it is persisted to traces."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "[redacted]"
_MAX_PERSISTED_STRING = 8192
_BINARY_KEY_SUFFIXES = ("_base64", "_b64")


def redact_arguments(arguments: Any) -> Any:
    """Keep argument names but drop their values."""
    if isinstance(arguments, Mapping):
        return {str(key): REDACTED for key in arguments}
    return REDACTED if arguments else arguments


def _slim(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_PERSISTED_STRING:
        return f"[omitted: {len(value)} characters]"
    return value


def prepare_tool_step(
    *,
    arguments: Any,
    result: Any,
    metadata: Mapping[str, Any] | None,
    sensitive: bool,
) -> tuple[Any, Any, dict[str, Any]]:
    """Return ``(arguments, result, metadata)`` safe to write to a trace store.

    For every tool, metadata values under binary-looking keys (``*_base64``,
    ``*_b64``) and very long strings are omitted. For sensitive tools (those
    that require confirmation), argument values, the result text, and the
    executor's copy of the arguments in metadata are redacted too.
    """
    clean: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if isinstance(key, str) and key.endswith(_BINARY_KEY_SUFFIXES):
            clean[key] = "[omitted]"
        else:
            clean[key] = _slim(value)

    if not sensitive:
        return arguments, _slim(result), clean

    if "arguments" in clean:
        clean["arguments"] = redact_arguments(clean["arguments"])
    return redact_arguments(arguments), (REDACTED if result else result), clean


__all__ = ["REDACTED", "prepare_tool_step", "redact_arguments"]
