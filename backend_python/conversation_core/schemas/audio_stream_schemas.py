from pydantic import BaseModel, Field


class AudioStreamSummary(BaseModel):
    event: str = "stream_complete"

    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    sample_width_bytes: int = Field(gt=0)

    chunk_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    total_samples: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)
