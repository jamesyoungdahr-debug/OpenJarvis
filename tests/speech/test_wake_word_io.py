"""Timing/behavior tests for continuous wake-word listening."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Optional

from openjarvis.speech._wake_stubs import WakeDetection, WakeWordBackend
from openjarvis.speech.wake_word_io import listen_for_wake_word


class _FakeStream:
    def __init__(self, frames: list[bytes]) -> None:
        self.frames = iter(frames)
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def read(self, chunk: int):
        self.reads += 1
        return next(self.frames), False


def _install_audio(monkeypatch, stream: _FakeStream) -> None:
    fake_sd = SimpleNamespace(RawInputStream=lambda **kwargs: stream)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)


class _FakeBackend(WakeWordBackend):
    """Test double: returns None for a scripted number of calls, then a hit."""

    backend_id = "fake"

    def __init__(self, hit_after: int) -> None:
        self._hit_after = hit_after
        self._calls = 0
        self.reset_calls = 0

    def process_frame(self, frame: bytes) -> Optional[WakeDetection]:
        self._calls += 1
        if self._calls >= self._hit_after:
            return WakeDetection(
                keyword="hey_jarvis", score=0.9, frame_index=self._calls
            )
        return None

    def frame_size(self) -> int:
        return 4

    def sample_rate(self) -> int:
        return 16000

    def health(self) -> bool:
        return True

    def reset(self) -> None:
        self.reset_calls += 1


def test_listen_for_wake_word_returns_detection_on_hit(monkeypatch) -> None:
    frame = bytes(4 * 2)
    stream = _FakeStream([frame, frame, frame, frame])
    _install_audio(monkeypatch, stream)

    backend = _FakeBackend(hit_after=4)
    detection = listen_for_wake_word(backend)

    assert detection is not None
    assert detection.keyword == "hey_jarvis"
    assert stream.reads == 4


def test_listen_for_wake_word_times_out(monkeypatch) -> None:
    frame = bytes(4 * 2)
    stream = _FakeStream([frame] * 100)
    _install_audio(monkeypatch, stream)

    backend = _FakeBackend(hit_after=1000)  # never hits
    detection = listen_for_wake_word(backend, max_seconds=0.025)

    assert detection is None
    expected_max_frames = int(0.025 * backend.sample_rate() / backend.frame_size())
    assert stream.reads == expected_max_frames


def test_listen_for_wake_word_calls_reset_before_loop(monkeypatch) -> None:
    frame = bytes(4 * 2)
    stream = _FakeStream([frame])
    _install_audio(monkeypatch, stream)

    backend = _FakeBackend(hit_after=1)
    listen_for_wake_word(backend)

    assert backend.reset_calls == 1


def test_listen_for_wake_word_raises_without_sounddevice(monkeypatch) -> None:
    import pytest

    monkeypatch.setitem(sys.modules, "sounddevice", None)

    backend = _FakeBackend(hit_after=1)
    with pytest.raises(RuntimeError, match="sounddevice"):
        listen_for_wake_word(backend)
