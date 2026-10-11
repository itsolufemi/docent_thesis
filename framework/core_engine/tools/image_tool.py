"""Configurable, domain-neutral image loading tool.

An application chooses a trusted root directory. The model may request only
relative paths beneath that directory; arbitrary paths and URLs are rejected.
Image bytes are carried separately from the JSON tool response.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core_engine.schemas.multimodal_schemas import ImageInput
from core_engine.schemas.tool_schemas import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
)
from core_engine.tools.tool_registry import ToolHandler


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024


class LoadImageArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_reference: str = Field(min_length=1, max_length=1024)


def detect_image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def read_allowed_image(
    image_reference: str,
    *,
    image_root: Path,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> ImageInput:
    """Load an image without allowing an LLM to access arbitrary files."""
    relative = Path(image_reference)
    if (
        relative.is_absolute()
        or PureWindowsPath(image_reference).is_absolute()
        or ":" in image_reference
        or "\x00" in image_reference
        or relative.suffix.lower() not in SUPPORTED_SUFFIXES
    ):
        raise ValueError("Invalid or unsupported image reference.")

    root = image_root.resolve()
    selected = (root / relative).resolve()
    if not selected.is_relative_to(root):
        raise ValueError("Image reference is outside the permitted directory.")
    if not selected.is_file():
        raise FileNotFoundError("The requested image is unavailable.")

    with selected.open("rb") as file:
        data = file.read(max_image_bytes + 1)
    if len(data) > max_image_bytes:
        raise ValueError("Image exceeds the configured size limit.")

    media_type = detect_image_type(data)
    if media_type is None:
        raise ValueError("Image contents are not supported JPEG, PNG, or WebP.")
    return ImageInput(data=data, media_type=media_type)


def create_image_tool(
    *,
    image_root: Path,
    name: str = "load_image",
    description: str | None = None,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> tuple[ToolDefinition, ToolHandler]:
    """Return a tool definition and handler bound to one application's images."""
    if max_image_bytes < 1:
        raise ValueError("max_image_bytes must be positive.")

    definition = ToolDefinition(
        name=name,
        allowed_phases={"primary"},
        description=description or (
            "Load a relevant image for visual inspection. Use an exact "
            "image_reference supplied by retrieval or trusted conversation "
            "context, not an invented path. The loaded image will be attached "
            "to your next model request. Use it when a question requires "
            "seeing an image rather than relying on its textual description."
        ),
        parameters={
            "type": "object",
            "properties": {
                "image_reference": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Exact relative image_reference previously provided "
                        "as trusted contextual or retrieved evidence."
                    ),
                }
            },
            "required": ["image_reference"],
            "additionalProperties": False,
        },
    )

    def load_image(
        context: ToolExecutionContext,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        del context
        validated = LoadImageArguments.model_validate(arguments)
        image = read_allowed_image(
            validated.image_reference,
            image_root=image_root,
            max_image_bytes=max_image_bytes,
        )
        return ToolExecutionResult(
            tool_name=definition.name,
            success=True,
            message="Image loaded; visual data attached to the next model request.",
            data={
                "image_reference": validated.image_reference,
                "media_type": image.media_type,
            },
            image_attachments=[image],
        )

    return definition, load_image
