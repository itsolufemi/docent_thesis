"""Provider-neutral inputs and outputs for image-and-text model requests."""

from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class ImageInput:
    data: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class MultimodalInput:
    question: str
    images: tuple[ImageInput, ...] = ()
    context: str | None = None


@dataclass(frozen=True, slots=True)
class ModelAnswer:
    text: str
    model: str


@dataclass(frozen=True, slots=True)
class MultimodalAnswer:
    text: str
    model: str
    image_count: int
    used_context: bool
    elapsed_seconds: float


class MultimodalQueryResponse(BaseModel):
    response: str
    model: str
    image_count: int
    used_context: bool
    elapsed_seconds: float
