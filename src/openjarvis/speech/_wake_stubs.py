"""Abstract base classes and data types for wake-word detection backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class WakeDetection:
    """Result of a single wake-word detection event."""

    keyword: str
    score: float
    frame_index: int = 0


class WakeWordBackend(ABC):
    """Abstract base class for wake-word detection backends."""

    backend_id: str = ""

    @abstractmethod
    def process_frame(self, frame: bytes) -> Optional[WakeDetection]:
        """Feed one PCM frame; return a WakeDetection if it fired, else None."""

    @abstractmethod
    def frame_size(self) -> int:
        """Exact number of int16 samples expected per process_frame() call."""

    @abstractmethod
    def sample_rate(self) -> int:
        """Sample rate (Hz) this backend expects audio to be captured at."""

    @abstractmethod
    def health(self) -> bool:
        """Check if the backend/model is ready."""

    @abstractmethod
    def reset(self) -> None:
        """Clear internal model state (e.g. between listening sessions)."""


__all__ = ["WakeDetection", "WakeWordBackend"]
