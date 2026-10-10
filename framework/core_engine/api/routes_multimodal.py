"""Experimental Swagger endpoint for provider-neutral text-and-image requests."""

import logging
from typing import Annotated

from pydantic import WithJsonSchema
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from core_engine.schemas.multimodal_schemas import (
    ImageInput,
    MultimodalInput,
    MultimodalQueryResponse,
)
from core_engine.services.multimodal_service import MultimodalService


logger = logging.getLogger(__name__)
MAX_IMAGE_COUNT = 4
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Swagger UI currently recognises format=binary, not contentMediaType.
# Keep the upload annotation non-nullable and use an empty default so
# OpenAPI renders a proper multiple-file chooser while files stay optional.
BinaryImageUpload = Annotated[
    UploadFile,
    WithJsonSchema({"type": "string", "format": "binary"}),
]


def detect_image_media_type(data: bytes) -> str | None:
    """Check image file signatures rather than trusting uploaded filenames."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def create_multimodal_router(service: MultimodalService) -> APIRouter:
    router = APIRouter(tags=["Multimodal (experimental)"])

    @router.post(
        "/api/llm/multimodal/query",
        response_model=MultimodalQueryResponse,
        summary="Ask a question with optional images and contextual text",
        description=(
            "Development-only model probe. Supply a question, optional "
            "reference text or caption, and up to four JPEG/PNG/WebP files. "
            "It does not use conversation history or perform retrieval."
        ),
    )
    async def query_multimodal(
        question: str = Form(min_length=1, max_length=4000),
        context: str | None = Form(default=None, max_length=20000),
        images: list[BinaryImageUpload] = File(default=[]),
    ) -> MultimodalQueryResponse:
        if not question.strip():
            raise HTTPException(status_code=422, detail="Question must not be blank.")

        files = images or []
        if len(files) > MAX_IMAGE_COUNT:
            raise HTTPException(
                status_code=413,
                detail=f"Upload at most {MAX_IMAGE_COUNT} images.",
            )

        image_inputs: list[ImageInput] = []
        for uploaded in files:
            try:
                data = await uploaded.read(MAX_IMAGE_BYTES + 1)
            finally:
                await uploaded.close()

            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Each image must be 10 MB or smaller.",
                )
            media_type = detect_image_media_type(data)
            if media_type is None:
                raise HTTPException(
                    status_code=415,
                    detail="Only JPEG, PNG, and WebP image files are accepted.",
                )
            image_inputs.append(ImageInput(data=data, media_type=media_type))

        request = MultimodalInput(
            question=question.strip(),
            images=tuple(image_inputs),
            context=context.strip() if context and context.strip() else None,
        )
        try:
            result = await run_in_threadpool(service.answer, request)
        except Exception:
            logger.exception("Multimodal model query failed.")
            raise HTTPException(
                status_code=502,
                detail="Multimodal model request failed; check server logs.",
            ) from None

        return MultimodalQueryResponse(
            response=result.text,
            model=result.model,
            image_count=result.image_count,
            used_context=result.used_context,
            elapsed_seconds=result.elapsed_seconds,
        )

    return router
