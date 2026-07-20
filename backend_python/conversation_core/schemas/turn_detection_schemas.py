from typing import Literal

from pydantic import BaseModel, Field


TurnDecisionType = Literal[
    "continue_listening",
    "await_more_speech",
    "finalise_turn",
]


class TurnDetectionRequest(BaseModel):
    partial_utterance: str
    is_speech_active: bool
    silence_duration_ms: int = Field(ge=0)
    previous_turns: list[str] = Field(default_factory=list)


class TurnDetectionResult(BaseModel):
    decision: TurnDecisionType
    should_call_trp: bool
    should_finalise_turn: bool
    silence_duration_ms: int
    trp_probability: float | None = None
    trp_prediction_seconds: float | None = None
    reason: str
