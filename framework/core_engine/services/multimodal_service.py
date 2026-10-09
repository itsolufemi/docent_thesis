"""Domain-neutral multimodal generation interface.

Retrieval, captioning, and domain-specific prompt construction remain the
responsibility of the calling application; this service receives optional
context as plain text.
"""

from time import perf_counter
from typing import Protocol

from core_engine.schemas.multimodal_schemas import (
    ModelAnswer,
    MultimodalAnswer,
    MultimodalInput,
)


class MultimodalProvider(Protocol):
    def generate(self, request: MultimodalInput) -> ModelAnswer:
        """Generate a response to a text-and-optional-images request."""
        ...


class MultimodalService:
    def __init__(self, provider: MultimodalProvider) -> None:
        self._provider = provider

    def answer(self, request: MultimodalInput) -> MultimodalAnswer:
        started = perf_counter()
        result = self._provider.generate(request)
        return MultimodalAnswer(
            text=result.text,
            model=result.model,
            image_count=len(request.images),
            used_context=bool(request.context),
            elapsed_seconds=round(perf_counter() - started, 4),
        )
