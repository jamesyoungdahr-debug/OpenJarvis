"""Tests for speech backend auto-discovery."""

from unittest.mock import MagicMock, call, patch

from openjarvis.core.config import JarvisConfig


def test_get_speech_backend_explicit():
    """Explicit backend selection works."""
    from openjarvis.speech._discovery import get_speech_backend

    config = JarvisConfig()
    config.speech.backend = "faster-whisper"

    with patch("openjarvis.speech._discovery._create_backend") as mock_create:
        mock_backend = type(
            "MockBackend",
            (),
            {
                "backend_id": "faster-whisper",
                "health": lambda self: True,
            },
        )()
        mock_create.return_value = mock_backend

        result = get_speech_backend(config)
        assert result is not None
        assert result.backend_id == "faster-whisper"


def test_get_speech_backend_returns_none_if_nothing_available():
    """Returns None when no backend can be created."""
    from openjarvis.speech._discovery import get_speech_backend

    config = JarvisConfig()
    config.speech.backend = "nonexistent"

    result = get_speech_backend(config)
    assert result is None


def test_auto_discovery_priority():
    """Auto mode tries backends in priority order."""
    from openjarvis.speech._discovery import DISCOVERY_ORDER

    assert DISCOVERY_ORDER[0] == "faster-whisper"
    assert "openai" in DISCOVERY_ORDER
    assert "deepgram" in DISCOVERY_ORDER


def test_auto_discovery_skips_unhealthy_backend() -> None:
    """Do not open the microphone for a backend that cannot transcribe."""
    from openjarvis.speech._discovery import get_speech_backend

    config = JarvisConfig()
    config.speech.backend = "auto"
    unhealthy = MagicMock(backend_id="faster-whisper")
    unhealthy.health.return_value = False
    healthy = MagicMock(backend_id="openai")
    healthy.health.return_value = True

    with patch(
        "openjarvis.speech._discovery._create_backend",
        side_effect=[unhealthy, healthy],
    ) as create:
        result = get_speech_backend(config)

    assert result is healthy
    assert create.call_args_list == [
        call("faster-whisper", config),
        call("openai", config),
    ]


def test_auto_discovery_continues_when_health_check_raises() -> None:
    from openjarvis.speech._discovery import get_speech_backend

    config = JarvisConfig()
    config.speech.backend = "auto"
    broken = MagicMock(backend_id="faster-whisper")
    broken.health.side_effect = RuntimeError("model cannot load")
    healthy = MagicMock(backend_id="openai")
    healthy.health.return_value = True

    with patch(
        "openjarvis.speech._discovery._create_backend",
        side_effect=[broken, healthy],
    ):
        assert get_speech_backend(config) is healthy


def test_explicit_unhealthy_backend_is_unavailable() -> None:
    from openjarvis.speech._discovery import get_speech_backend

    config = JarvisConfig()
    config.speech.backend = "faster-whisper"
    backend = MagicMock()
    backend.health.return_value = False

    with patch(
        "openjarvis.speech._discovery._create_backend",
        return_value=backend,
    ):
        assert get_speech_backend(config) is None


def test_get_wake_word_backend_disabled_by_default() -> None:
    """An empty wake_word means the feature is off -- registry is never consulted."""
    from openjarvis.speech._discovery import get_wake_word_backend

    config = JarvisConfig()
    assert config.speech.wake_word == ""

    with patch("openjarvis.core.registry.WakeWordRegistry.contains") as mock_contains:
        result = get_wake_word_backend(config)

    assert result is None
    mock_contains.assert_not_called()


def test_get_wake_word_backend_resolves_when_enabled() -> None:
    from openjarvis.speech._discovery import get_wake_word_backend

    config = JarvisConfig()
    config.speech.wake_word = "hey_jarvis"

    mock_backend = MagicMock()
    mock_backend.health.return_value = True
    mock_backend_cls = MagicMock(return_value=mock_backend)

    with (
        patch("openjarvis.core.registry.WakeWordRegistry.contains", return_value=True),
        patch(
            "openjarvis.core.registry.WakeWordRegistry.get",
            return_value=mock_backend_cls,
        ),
    ):
        result = get_wake_word_backend(config)

    assert result is mock_backend
    mock_backend_cls.assert_called_once_with(keyword="hey_jarvis", sensitivity=0.5)


def test_get_wake_word_backend_unhealthy_returns_none() -> None:
    from openjarvis.speech._discovery import get_wake_word_backend

    config = JarvisConfig()
    config.speech.wake_word = "hey_jarvis"

    mock_backend = MagicMock()
    mock_backend.health.return_value = False
    mock_backend_cls = MagicMock(return_value=mock_backend)

    with (
        patch("openjarvis.core.registry.WakeWordRegistry.contains", return_value=True),
        patch(
            "openjarvis.core.registry.WakeWordRegistry.get",
            return_value=mock_backend_cls,
        ),
    ):
        result = get_wake_word_backend(config)

    assert result is None


def test_get_wake_word_backend_unknown_registry_key_returns_none() -> None:
    from openjarvis.speech._discovery import get_wake_word_backend

    config = JarvisConfig()
    config.speech.wake_word = "hey_jarvis"
    config.speech.wake_word_backend = "nonexistent"

    result = get_wake_word_backend(config)

    assert result is None
