from pydantic import BaseModel, Field

from conversation_core.schemas.turn_detection_schemas import TurnDecisionType


class TurnBufferState(BaseModel):
    conversation_id: str
    transcript: str = ""
    is_speech_active: bool = False
    silence_duration_ms: int = 0
    last_evaluated_transcript: str | None = None
    last_trp_probability: float | None = None
    is_finalised: bool = False


class TurnBufferEvent(BaseModel):
    conversation_id: str
    partial_utterance: str
    is_speech_active: bool
    silence_duration_ms: int = Field(ge=0)


class TurnBufferResult(BaseModel):
    state: TurnBufferState
    decision: TurnDecisionType
    should_finalise_turn: bool
    finalised_utterance: str | None = None
    reason: str
