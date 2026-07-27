from pydantic import BaseModel, Field


class SynthesisRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=10_000,
    )
    voice: str = "bf_emma"
    speed: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
    )
