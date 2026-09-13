"""Tests for openWakeWord wake-word detection backend."""

from unittest.mock import MagicMock, patch

import pytest

from openjarvis.core.registry import WakeWordRegistry
from openjarvis.speech.openwakeword_backend import OpenWakeWordBackend


@pytest.fixture(autouse=True)
def _register_openwakeword():
    """Re-register after any registry clear."""
    if not WakeWordRegistry.contains("openwakeword"):
        WakeWordRegistry.register_value("openwakeword", OpenWakeWordBackend)


def test_openwakeword_backend_registers():
    """Backend registers itself in WakeWordRegistry."""
    assert WakeWordRegistry.contains("openwakeword")


def test_process_frame_detects_above_threshold():
    mock_model = MagicMock()
    mock_model.predict.return_value = {"hey_jarvis": 0.9}

    with patch(
        "openjarvis.speech.openwakeword_backend._OWWModel",
        return_value=mock_model,
    ):
        backend = OpenWakeWordBackend(keyword="hey_jarvis", sensitivity=0.5)
        detection = backend.process_frame(b"\x00\x00" * 1280)

        assert detection is not None
        assert detection.keyword == "hey_jarvis"
        assert detection.score == 0.9
        assert detection.frame_index == 1


def test_process_frame_below_threshold_returns_none():
    mock_model = MagicMock()
    mock_model.predict.return_value = {"hey_jarvis": 0.1}

    with patch(
        "openjarvis.speech.openwakeword_backend._OWWModel",
        return_value=mock_model,
    ):
        backend = OpenWakeWordBackend(keyword="hey_jarvis", sensitivity=0.5)
        detection = backend.process_frame(b"\x00\x00" * 1280)

        assert detection is None


def test_process_frame_falls_back_to_sole_score_when_key_mismatched():
    mock_model = MagicMock()
    mock_model.predict.return_value = {"some_other_model_name": 0.8}

    with patch(
        "openjarvis.speech.openwakeword_backend._OWWModel",
        return_value=mock_model,
    ):
        backend = OpenWakeWordBackend(keyword="hey_jarvis", sensitivity=0.5)
        detection = backend.process_frame(b"\x00\x00" * 1280)

        assert detection is not None
        assert detection.score == 0.8


def test_frame_size_and_sample_rate():
    backend = OpenWakeWordBackend()
    assert backend.frame_size() == 1280
    assert backend.sample_rate() == 16000


def test_health_missing_dependency():
    with patch("openjarvis.speech.openwakeword_backend._OWWModel", new=None):
        backend = OpenWakeWordBackend()
        assert backend.health() is False
        assert "wake-word" in (backend.last_error() or "")


def test_health_captures_load_error():
    with patch(
        "openjarvis.speech.openwakeword_backend._OWWModel",
        side_effect=RuntimeError("model download failed"),
    ):
        backend = OpenWakeWordBackend()
        assert backend.health() is False
        assert "model download failed" in (backend.last_error() or "")


def test_health_ok_when_model_loads():
    mock_model = MagicMock()
    with patch(
        "openjarvis.speech.openwakeword_backend._OWWModel",
        return_value=mock_model,
    ):
        backend = OpenWakeWordBackend()
        assert backend.health() is True


def test_reset_calls_model_reset():
    mock_model = MagicMock()
    with patch(
        "openjarvis.speech.openwakeword_backend._OWWModel",
        return_value=mock_model,
    ):
        backend = OpenWakeWordBackend()
        backend._ensure_model()
        backend.reset()
        mock_model.reset.assert_called_once()


def test_reset_before_model_loaded_does_not_raise():
    backend = OpenWakeWordBackend()
    backend.reset()  # should not raise even though no model has been loaded yet
