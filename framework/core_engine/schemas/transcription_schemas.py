from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str


class TranscriptionResponse(BaseModel):
    text: str

    language: str | None = None
    language_probability: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )

    duration_seconds: float | None = Field(
        default=None,
        ge=0,
    )

    segments: list[TranscriptionSegment] = Field(
        default_factory=list,
    )
