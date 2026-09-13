"""Auto-discover available speech-to-text backends."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from openjarvis.core.config import JarvisConfig
    from openjarvis.speech._stubs import SpeechBackend
    from openjarvis.speech._wake_stubs import WakeWordBackend

# Priority order: local first, then cloud
DISCOVERY_ORDER = [
    "faster-whisper",
    "openai",
    "deepgram",
]


def _create_backend(
    key: str,
    config: "JarvisConfig",
) -> Optional["SpeechBackend"]:
    """Try to instantiate a speech backend by registry key."""
    from openjarvis.core.registry import SpeechRegistry

    if not SpeechRegistry.contains(key):
        return None

    try:
        backend_cls = SpeechRegistry.get(key)

        if key == "faster-whisper":
            return backend_cls(
                model_size=config.speech.model,
                device=config.speech.device,
                compute_type=config.speech.compute_type,
            )
        elif key == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return None
            return backend_cls(api_key=api_key)
        elif key == "deepgram":
            api_key = os.environ.get("DEEPGRAM_API_KEY", "")
            if not api_key:
                return None
            return backend_cls(api_key=api_key)
        else:
            return backend_cls()
    except Exception:
        return None


def get_speech_backend(config: "JarvisConfig") -> Optional["SpeechBackend"]:
    """Resolve the speech backend from config.

    If ``config.speech.backend`` is ``"auto"``, tries backends in
    priority order and returns the first healthy one.
    """
    # Trigger registration of built-in backends
    import openjarvis.speech  # noqa: F401

    backend_key = config.speech.backend

    if backend_key != "auto":
        backend = _create_backend(backend_key, config)
        if backend is None:
            return None
        try:
            return backend if backend.health() else None
        except Exception:
            return None

    # Auto-discovery: try each in priority order
    for key in DISCOVERY_ORDER:
        backend = _create_backend(key, config)
        if backend is None:
            continue
        try:
            if backend.health():
                return backend
        except Exception:
            continue

    return None


def get_wake_word_backend(config: "JarvisConfig") -> Optional["WakeWordBackend"]:
    """Resolve the configured wake-word backend, or None if disabled/unavailable.

    No auto-discovery across engines (only one implementation exists today) --
    this only instantiates a backend when config.speech.wake_word is
    non-empty, which is the feature's on/off switch.
    """
    if not config.speech.wake_word:
        return None

    import openjarvis.speech  # noqa: F401 -- trigger registration
    from openjarvis.core.registry import WakeWordRegistry

    key = config.speech.wake_word_backend
    if not WakeWordRegistry.contains(key):
        return None

    try:
        backend_cls = WakeWordRegistry.get(key)
        backend = backend_cls(
            keyword=config.speech.wake_word,
            sensitivity=config.speech.wake_word_sensitivity,
        )
        return backend if backend.health() else None
    except Exception:
        return None
