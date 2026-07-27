from pydantic import BaseModel, Field


class TextToSpeechRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=5_000,
    )
    voice_name: str | None = None
    language_code: str | None = None
