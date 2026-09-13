"""Tests for wake-word ABC and data types."""

from openjarvis.speech._wake_stubs import WakeDetection, WakeWordBackend


def test_wake_detection():
    detection = WakeDetection(keyword="hey_jarvis", score=0.87, frame_index=42)
    assert detection.keyword == "hey_jarvis"
    assert detection.score == 0.87
    assert detection.frame_index == 42


def test_wake_detection_default_frame_index():
    detection = WakeDetection(keyword="hey_jarvis", score=0.6)
    assert detection.frame_index == 0


def test_wake_word_backend_is_abstract():
    import pytest

    with pytest.raises(TypeError):
        WakeWordBackend()
