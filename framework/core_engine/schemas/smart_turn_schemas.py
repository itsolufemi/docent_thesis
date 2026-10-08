from pydantic import BaseModel, Field


class SmartTurnResult(BaseModel):
    completion_probability: float = Field(
        ge=0.0,
        le=1.0,
    )
    turn_complete: bool
    feature_extraction_seconds: float
    inference_seconds: float
    total_seconds: float

