"""Provider-specific conversion of generic image attachments to Ollama input."""

import base64

from core_engine.schemas.multimodal_schemas import ImageInput


def build_ollama_image_followup(images: list[ImageInput]) -> dict:
    """An Ollama-compatible user message containing tool-loaded image bytes."""
    return {
        "role": "user",
        "content": (
            "The requested image has been loaded for your existing question. "
            "Inspect the attached image and continue answering the original "
            "request. Do not treat this message as a new visitor question."
        ),
        "images": [base64.b64encode(image.data).decode("ascii") for image in images],
    }
