"""Tests for trace redaction of tool steps."""

from __future__ import annotations

from openjarvis.traces.redaction import REDACTED, prepare_tool_step, redact_arguments


def test_non_sensitive_step_is_kept():
    arguments, result, metadata = prepare_tool_step(
        arguments={"expr": "2+2"},
        result="4",
        metadata={"skill": "math", "skill_source": "builtin"},
        sensitive=False,
    )

    assert arguments == {"expr": "2+2"}
    assert result == "4"
    assert metadata == {"skill": "math", "skill_source": "builtin"}


def test_binary_metadata_is_omitted_for_every_tool():
    _, _, metadata = prepare_tool_step(
        arguments={},
        result="Screenshot taken",
        metadata={"screenshot_base64": "iVBORw0KGgo=", "thumb_b64": "abc", "w": 10},
        sensitive=False,
    )

    assert metadata == {
        "screenshot_base64": "[omitted]",
        "thumb_b64": "[omitted]",
        "w": 10,
    }


def test_long_strings_are_omitted_but_short_ones_kept():
    long_text = "x" * 9000
    _, result, metadata = prepare_tool_step(
        arguments={},
        result=long_text,
        metadata={"note": long_text, "short": "ok"},
        sensitive=False,
    )

    assert result == "[omitted: 9000 characters]"
    assert metadata == {"note": "[omitted: 9000 characters]", "short": "ok"}


def test_sensitive_step_redacts_arguments_result_and_metadata_copy():
    arguments, result, metadata = prepare_tool_step(
        arguments={"to": ["a@example.com"], "body": "secret plans"},
        result="Sent 'Hi' to a@example.com.",
        metadata={"arguments": {"to": ["a@example.com"], "body": "secret plans"}},
        sensitive=True,
    )

    assert arguments == {"to": REDACTED, "body": REDACTED}
    assert result == REDACTED
    assert metadata == {"arguments": {"to": REDACTED, "body": REDACTED}}


def test_sensitive_empty_result_stays_empty():
    _, result, _ = prepare_tool_step(
        arguments={}, result="", metadata=None, sensitive=True
    )

    assert result == ""


def test_redact_arguments_handles_non_mapping_values():
    assert redact_arguments('{"text": "hunter2"}') == REDACTED
    assert redact_arguments("") == ""
    assert redact_arguments(None) is None
