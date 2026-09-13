"""openWakeWord wake-word detection backend (local, ONNX-based)."""

from __future__ import annotations

import logging
import os
from typing import Optional

from openjarvis.core.registry import WakeWordRegistry
from openjarvis.speech._wake_stubs import WakeDetection, WakeWordBackend

try:
    from openwakeword.model import Model as _OWWModel
except ImportError:
    _OWWModel = None  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_FRAME_SIZE = 1280  # 80ms @ 16kHz -- openWakeWord's feature pipeline requires this


@WakeWordRegistry.register("openwakeword")
class OpenWakeWordBackend(WakeWordBackend):
    """Local wake-word detection using openWakeWord (ONNX runtime)."""

    backend_id = "openwakeword"

    def __init__(
        self,
        keyword: str = "hey_jarvis",
        sensitivity: float = 0.5,
    ) -> None:
        self._keyword = keyword or "hey_jarvis"
        self._sensitivity = sensitivity
        self._model = None
        self._last_error: Optional[str] = None
        self._frame_index = 0

    def _model_key(self) -> str:
        """The dict key openWakeWord uses in predict()'s return value for our model.

        openWakeWord keys predictions by the model's basename without extension
        (e.g. "hey_jarvis" for both the shorthand and a full path ending in
        hey_jarvis.onnx/.tflite). Shorthand names and basenames coincide for
        the bundled models we support, so this is a direct passthrough.
        """
        return os.path.splitext(os.path.basename(self._keyword))[0]

    def _ensure_model(self):
        """Lazy-load the openWakeWord model on first use."""
        if self._model is None:
            if _OWWModel is None:
                self._last_error = (
                    "openwakeword is not installed. "
                    "Install with: pip install 'OpenJarvis[wake-word]'"
                )
                raise ImportError(self._last_error)
            self._model = _OWWModel(wakeword_models=[self._keyword])
        self._last_error = None
        return self._model

    def process_frame(self, frame: bytes) -> Optional[WakeDetection]:
        """Feed one PCM frame to the model; return a WakeDetection if it fired."""
        import numpy as np

        try:
            model = self._ensure_model()
            samples = np.frombuffer(frame, dtype=np.int16)
            predictions = model.predict(samples)
            self._frame_index += 1
            key = self._model_key()
            score = predictions.get(key)
            if score is None and predictions:
                # Fallback: single-model configs sometimes key differently
                # across openWakeWord versions; use the only available score.
                score = next(iter(predictions.values()))
            if score is not None and score > self._sensitivity:
                return WakeDetection(
                    keyword=self._keyword,
                    score=float(score),
                    frame_index=self._frame_index,
                )
            return None
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def frame_size(self) -> int:
        """Exact number of int16 samples expected per process_frame() call."""
        return _FRAME_SIZE

    def sample_rate(self) -> int:
        """Sample rate (Hz) this backend expects audio to be captured at."""
        return _SAMPLE_RATE

    def health(self) -> bool:
        """Check if model is loaded or loadable."""
        try:
            self._ensure_model()
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("openWakeWord health check failed: %s", exc)
            return False

    def reset(self) -> None:
        """Clear internal model state (e.g. between listening sessions)."""
        if self._model is not None:
            try:
                self._model.reset()
            except Exception:
                pass
        self._frame_index = 0

    def last_error(self) -> Optional[str]:
        """Return the last model load or inference error, if any."""
        return self._last_error
