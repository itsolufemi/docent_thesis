"""Ollama-specific transport for the generic multimodal contract."""

import base64

from config import settings
from core_engine.schemas.multimodal_schemas import ModelAnswer, MultimodalInput
from core_engine.services.llm_service import send_ollama_chat_request


class OllamaMultimodalProvider:
    def generate(self, request: MultimodalInput) -> ModelAnswer:
        content = request.question.strip()
        if request.context and request.context.strip():
            content = (
                "Additional reference context (which may be incomplete):\n"
                f"{request.context.strip()}\n\n"
                f"Question:\n{content}"
            )

        message: dict = {"role": "user", "content": content}
        if request.images:
            message["images"] = [
                base64.b64encode(image.data).decode("ascii")
                for image in request.images
            ]

        response = send_ollama_chat_request(messages=[message])
        answer = (response.get("message") or {}).get("content") or ""
        answer = answer.strip()
        if not answer:
            raise RuntimeError("The selected model returned no answer.")

        return ModelAnswer(
            text=answer,
            model=response.get("model") or settings.ollama_model,
        )
