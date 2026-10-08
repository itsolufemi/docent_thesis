from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SmartTurnPrediction:
    completion_probability: float
    turn_complete: bool
    feature_extraction_seconds: float
    inference_seconds: float
    total_seconds: float


class SmartTurnService(Protocol):
    def warm_up(self) -> float:
        ...

    def predict(
        self,
        pcm_audio: bytes,
        sample_rate: int = 16_000,
        *,
        channels: int = 1,
    ) -> SmartTurnPrediction:
        ...
