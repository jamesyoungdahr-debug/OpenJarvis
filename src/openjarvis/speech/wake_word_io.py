"""Continuous microphone monitoring for wake-word detection."""

from __future__ import annotations

from typing import Optional

from openjarvis.speech._wake_stubs import WakeDetection, WakeWordBackend

_CHANNELS = 1


def listen_for_wake_word(
    backend: WakeWordBackend,
    *,
    max_seconds: Optional[float] = None,
) -> Optional[WakeDetection]:
    """Block until the wake word fires, or ``max_seconds`` elapses.

    Opens its own ``sounddevice.RawInputStream`` sized to
    ``backend.sample_rate()`` / ``backend.frame_size()``, feeds frames to
    ``backend.process_frame()``, and returns as soon as a WakeDetection is
    produced. The stream is always closed (via ``with``) before this function
    returns -- including on detection -- so callers are free to immediately
    open a second, independent stream (e.g. via
    ``openjarvis.speech.voice_io.record_until_silence``) without contention.

    Returns None if ``max_seconds`` elapses with no detection (None means
    listen forever). Raises RuntimeError if sounddevice is not installed.
    KeyboardInterrupt propagates to the caller uncaught (mirrors
    record_until_silence's contract, letting callers like _voice_chat.py map
    it to their own exit sentinel).
    """
    try:
        import sounddevice as sd
    except ImportError:
        raise RuntimeError(
            "sounddevice is required for wake-word listening. "
            "Install with: pip install sounddevice"
        )

    sample_rate = backend.sample_rate()
    frame_size = backend.frame_size()
    backend.reset()

    max_frames = (
        int(max_seconds * sample_rate / frame_size) if max_seconds is not None else None
    )

    with sd.RawInputStream(
        samplerate=sample_rate,
        channels=_CHANNELS,
        dtype="int16",
        blocksize=frame_size,
    ) as stream:
        frames_read = 0
        while max_frames is None or frames_read < max_frames:
            raw, _ = stream.read(frame_size)
            frames_read += 1
            detection = backend.process_frame(bytes(raw))
            if detection is not None:
                return detection

    return None


__all__ = ["listen_for_wake_word"]
