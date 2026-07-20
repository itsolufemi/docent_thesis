from pydantic import BaseModel, Field


class TRPPredictionRequest(BaseModel):
    partial_utterance: str
    previous_turns: list[str] = Field(default_factory=list)


class TRPPrediction(BaseModel):
    trp_probability: float = Field(ge=0.0, le=1.0)
    turn_complete: bool
    reason: str
    prediction_seconds: float = 0.0
