import asyncio
import logging
from collections.abc import Callable, Iterable, Sequence
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from core_engine.api.routes_audio_stream import create_audio_stream_router
from core_engine.api.routes_conversation import create_conversation_router
from core_engine.api.routes_health import router as health_router
from core_engine.api.routes_llm import router as llm_router
from core_engine.api.routes_query import create_query_router
from core_engine.api.routes_transcription import create_transcription_router
from core_engine.api.routes_trp import router as trp_router
from core_engine.api.routes_tts import create_tts_router
from core_engine.api.routes_tts_stream import create_tts_stream_router
from core_engine.api.routes_turn_buffer import create_turn_buffer_router
from core_engine.api.routes_turn_buffer_stream import (
    create_turn_buffer_stream_router,
)
from core_engine.api.routes_turn_detection import (
    router as turn_detection_router,
)
from core_engine.api.routes_utterance_router import create_utterance_router
from core_engine.schemas.classifier_domain_schemas import (
    ClassifierDomainProfile,
)
from core_engine.services.llm_service import warm_up_main_llm
from core_engine.services.ollama_http_client import close_ollama_http_client
from core_engine.services.query_service import QueryEngine
from models.smart_turn.smart_turn_model_service import OnnxSmartTurnService
from models.transcription_factory import default_transcription_stack
from models.tts_factory import default_tts_service


logger = logging.getLogger("uvicorn.error")
WarmUpOperation = tuple[str, Callable[[], Any]]


async def _run_warm_up(
    name: str,
    operation: Callable[[], Any],
) -> dict[str, Any]:
    started_at = perf_counter()

    try:
        detail = await asyncio.to_thread(operation)
        result = {
            "name": name,
            "success": True,
            "seconds": round(perf_counter() - started_at, 4),
            "detail": detail,
        }
        logger.info(
            "%s warm-up completed in %.3f seconds.",
            name,
            result["seconds"],
        )
        return result
    except Exception as error:
        elapsed_seconds = perf_counter() - started_at
        logger.exception(
            "%s warm-up failed after %.3f seconds. The service will continue.",
            name,
            elapsed_seconds,
        )
        return {
            "name": name,
            "success": False,
            "seconds": round(elapsed_seconds, 4),
            "error": str(error),
        }


def create_framework_app(
    *,
    title: str,
    query_engine: QueryEngine,
    domain_profile: ClassifierDomainProfile,
    application_routers: Iterable[APIRouter] = (),
    application_warm_up_operations: Sequence[WarmUpOperation] = (),
    version: str = "0.1.0",
) -> FastAPI:
    """Compose the framework API with injected application capabilities."""
    smart_turn_service = (
        OnnxSmartTurnService(
            model_path=settings.smart_turn_model_path,
            threshold=settings.smart_turn_threshold,
            max_audio_seconds=settings.smart_turn_max_audio_seconds,
        )
        if settings.smart_turn_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        startup_started_at = perf_counter()
        warm_up_operations: list[WarmUpOperation] = []

        transcription_warm_up_settings = {
            "moonshine": settings.warm_up_moonshine_on_startup,
            "whisper": settings.warm_up_whisper_on_startup,
            "qmul_whisper": settings.warm_up_qmul_whisper_on_startup,
        }
        transcription_warm_up_enabled = transcription_warm_up_settings.get(
            settings.transcription_backend
        )
        if transcription_warm_up_enabled:
            warm_up_operations.append(
                (
                    default_transcription_stack.provider_name,
                    default_transcription_stack.warm_up,
                )
            )
        elif transcription_warm_up_enabled is None:
            logger.warning(
                "Unknown transcription backend configured: %s",
                settings.transcription_backend,
            )

        if (
            smart_turn_service is not None
            and settings.warm_up_smart_turn_on_startup
        ):
            warm_up_operations.append(
                ("Smart Turn", smart_turn_service.warm_up)
            )

        warm_up_operations.extend(application_warm_up_operations)

        if settings.warm_up_llm_on_startup:
            warm_up_operations.append(("Main LLM", warm_up_main_llm))

        if settings.warm_up_tts_on_startup:
            warm_up_operations.append(
                ("Selected streaming TTS", default_tts_service.warm_up)
            )

        results = await asyncio.gather(
            *[
                _run_warm_up(name, operation)
                for name, operation in warm_up_operations
            ]
        )
        logger.info(
            "Application warm-up completed in %.3f seconds: %s",
            perf_counter() - startup_started_at,
            results,
        )

        try:
            logger.info(
                "Selected TTS backend: %s",
                default_tts_service.provider_name,
            )
            yield
        finally:
            default_transcription_stack.close()
            default_tts_service.close()
            close_ollama_http_client()

    app = FastAPI(title=title, version=version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-TTS-Provider",
            "X-TTS-Voice",
            "X-TTS-Language",
            "X-TTS-Sample-Rate",
            "X-TTS-Characters",
            "X-TTS-Generation-Seconds",
        ],
    )

    framework_routers = [
        health_router,
        create_query_router(query_engine=query_engine),
        llm_router,
        create_conversation_router(query_engine=query_engine),
        create_utterance_router(domain_profile=domain_profile),
        trp_router,
        turn_detection_router,
        create_turn_buffer_router(
            query_engine=query_engine,
            utterance_classifier=None,
        ),
        create_turn_buffer_stream_router(
            query_engine=query_engine,
            utterance_classifier=None,
        ),
        create_transcription_router(
            default_transcription_stack.batch_service
        ),
        create_audio_stream_router(
            transcription_service=(
                default_transcription_stack.live_fallback_service
            ),
            smart_turn_service=smart_turn_service,
            streaming_transcription_service=(
                default_transcription_stack.streaming_service
            ),
        ),
        create_tts_router(default_tts_service),
        create_tts_stream_router(default_tts_service),
    ]

    for router in framework_routers:
        app.include_router(router)

    for router in application_routers:
        app.include_router(router)

    return app
