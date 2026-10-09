"""Unit tests for the domain-neutral multimodal probe (no model required)."""

import base64
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core_engine.api.routes_multimodal import create_multimodal_router
from core_engine.schemas.multimodal_schemas import ModelAnswer, MultimodalInput
from core_engine.services.multimodal_service import MultimodalService
from models.ollama_multimodal_provider import OllamaMultimodalProvider


PNG = b"\x89PNG\r\n\x1a\n" + b"unit-test-image"


class FakeProvider:
    def __init__(self) -> None:
        self.received: MultimodalInput | None = None

    def generate(self, request: MultimodalInput) -> ModelAnswer:
        self.received = request
        return ModelAnswer(text="The equation is correct.", model="fake-vision")


def make_client(provider: FakeProvider) -> TestClient:
    app = FastAPI()
    app.include_router(create_multimodal_router(MultimodalService(provider)))
    return TestClient(app)


def test_upload_and_context_reach_generic_provider() -> None:
    provider = FakeProvider()
    client = make_client(provider)

    response = client.post(
        "/api/llm/multimodal/query",
        data={"question": "Check this working.", "context": "Algebra notes"},
        files=[("images", ("math.png", PNG, "image/png"))],
    )

    assert response.status_code == 200
    assert response.json()["response"] == "The equation is correct."
    assert response.json()["image_count"] == 1
    assert response.json()["used_context"] is True
    assert provider.received is not None
    assert provider.received.images[0].data == PNG
    assert provider.received.images[0].media_type == "image/png"
    assert provider.received.context == "Algebra notes"


def test_text_only_is_supported() -> None:
    provider = FakeProvider()
    response = make_client(provider).post(
        "/api/llm/multimodal/query",
        data={"question": "Hello"},
    )
    assert response.status_code == 200
    assert response.json()["image_count"] == 0
    assert provider.received is not None
    assert provider.received.images == ()


def test_invalid_file_type_is_rejected_before_model_call() -> None:
    provider = FakeProvider()
    response = make_client(provider).post(
        "/api/llm/multimodal/query",
        data={"question": "What is this?"},
        files=[("images", ("notes.txt", b"not an image", "text/plain"))],
    )
    assert response.status_code == 415
    assert provider.received is None


def test_oversized_file_is_rejected() -> None:
    provider = FakeProvider()
    response = make_client(provider).post(
        "/api/llm/multimodal/query",
        data={"question": "What is this?"},
        files=[("images", ("large.png", PNG + b"x" * (10 * 1024 * 1024), "image/png"))],
    )
    assert response.status_code == 413
    assert provider.received is None


def test_ollama_adapter_encodes_image_without_leaking_provider_details_to_core() -> None:
    request = MultimodalInput(
        question="What do the birds represent?",
        context="Some artwork context",
        images=(
            __import__("core_engine.schemas.multimodal_schemas", fromlist=["ImageInput"])
            .ImageInput(data=PNG, media_type="image/png"),
        ),
    )
    with patch(
        "models.ollama_multimodal_provider.send_ollama_chat_request",
        return_value={
            "model": "vision-test-model",
            "message": {"content": "They might suggest freedom."},
        },
    ) as mocked:
        answer = OllamaMultimodalProvider().generate(request)

    assert answer.model == "vision-test-model"
    assert answer.text == "They might suggest freedom."
    message = mocked.call_args.kwargs["messages"][0]
    assert message["images"] == [base64.b64encode(PNG).decode("ascii")]
    assert "Some artwork context" in message["content"]
