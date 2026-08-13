#tagged

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings

from conversation_core.api.routes_audio_stream import (
    create_audio_stream_router,
)
from conversation_core.api.routes_conversation import (
    create_conversation_router,
)
from conversation_core.api.routes_health import router as health_router
from conversation_core.api.routes_llm import router as llm_router
from conversation_core.api.routes_query import create_query_router
from conversation_core.api.routes_trp import router as trp_router
from conversation_core.api.routes_transcription import (
    create_transcription_router,
)
from conversation_core.api.routes_tts import (
    create_tts_router,
)
from conversation_core.api.routes_tts_stream import (
    create_tts_stream_router,
)
from conversation_core.api.routes_turn_buffer import (
    create_turn_buffer_router,
)
from conversation_core.api.routes_turn_buffer_stream import (
    create_turn_buffer_stream_router,
)
from conversation_core.api.routes_turn_detection import (
    router as turn_detection_router,
)
from conversation_core.api.routes_utterance_router import (
    router as utterance_router,
)
from conversation_core.services.smart_turn_service import (
    SmartTurnService,
)
from conversation_core.services.tts_service_factory import (
    default_tts_service,
)
from conversation_core.services.llm_service import (
    warm_up_main_llm,
)
from conversation_core.services.ollama_http_client import (
    close_ollama_http_client,
)
from models.transcription_factory import (
    default_transcription_stack,
)
from docent.api.routes_artworks import router as artworks_router
from docent.api.routes_docent_index import router as docent_index_router
from docent.api.routes_docent_retrieval import router as docent_retrieval_router
from docent.services.docent_query_service import (
    context_resolved_docent_query_engine,
)
from docent.services.docent_vector_retrieval_service import (
    warm_up_docent_retrieval,
)
from docent.api.routes_docent_embeddings import router as docent_embeddings_router
from docent.api.routes_docent_vector import router as docent_vector_router


logger = logging.getLogger("uvicorn.error")


async def run_warm_up(
    name: str,
    operation: Callable[[], Any],
) -> dict:
    started_at = perf_counter()

    try:
        detail = await asyncio.to_thread(operation)
        result = {
            "name": name,
            "success": True,
            "seconds": round(
                perf_counter() - started_at,
                4,
            ),
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
            "%s warm-up failed after %.3f seconds. "
            "The service will continue.",
            name,
            elapsed_seconds,
        )
        return {
            "name": name,
            "success": False,
            "seconds": round(elapsed_seconds, 4),
            "error": str(error),
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_started_at = perf_counter()
    warm_up_operations: list[
        tuple[str, Callable[[], Any]]
    ] = []

    if (
        settings.transcription_backend == "moonshine"
        and settings.warm_up_moonshine_on_startup
    ):
        warm_up_operations.append(
            (
                default_transcription_stack.provider_name,
                default_transcription_stack.warm_up,
            )
        )
    elif (
        settings.transcription_backend == "whisper"
        and settings.warm_up_whisper_on_startup
    ):
        warm_up_operations.append(
            (
                default_transcription_stack.provider_name,
                default_transcription_stack.warm_up,
            )
        )
    elif (
        settings.transcription_backend == "qmul_whisper"
        and settings.warm_up_qmul_whisper_on_startup
    ):
        warm_up_operations.append(
            (
                default_transcription_stack.provider_name,
                default_transcription_stack.warm_up,
            )
        )
    elif settings.transcription_backend not in {
        "moonshine",
        "whisper",
        "qmul_whisper",
    }:
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

    if settings.warm_up_retrieval_on_startup:
        warm_up_operations.append(
            ("Docent retrieval", warm_up_docent_retrieval)
        )

    if settings.warm_up_llm_on_startup:
        warm_up_operations.append(
            ("Main LLM", warm_up_main_llm)
        )

    if settings.warm_up_tts_on_startup:
        warm_up_operations.append(
            (
                "Selected streaming TTS",
                default_tts_service.warm_up,
            )
        )

    results = await asyncio.gather(
        *[
            run_warm_up(name, operation)
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


app = FastAPI(
    title="docent backend",
    version="0.1.0",
    lifespan=lifespan,
)

permitted_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

tts_response_headers = [
    "X-TTS-Provider",
    "X-TTS-Voice",
    "X-TTS-Language",
    "X-TTS-Sample-Rate",
    "X-TTS-Characters",
    "X-TTS-Generation-Seconds",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=permitted_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=tts_response_headers,
)

query_router = create_query_router(
    query_engine=context_resolved_docent_query_engine,
)
conversation_router = create_conversation_router(
    query_engine=context_resolved_docent_query_engine,
)
turn_buffer_router = create_turn_buffer_router(
    query_engine=context_resolved_docent_query_engine,
    utterance_classifier=None,
)
turn_buffer_stream_router = create_turn_buffer_stream_router(
    query_engine=context_resolved_docent_query_engine,
    utterance_classifier=None,
)
transcription_router = create_transcription_router(
    default_transcription_stack.batch_service
)
smart_turn_service = (
    SmartTurnService(
        model_path=settings.smart_turn_model_path,
        threshold=settings.smart_turn_threshold,
        max_audio_seconds=(
            settings.smart_turn_max_audio_seconds
        ),
    )
    if settings.smart_turn_enabled
    else None
)

audio_stream_router = create_audio_stream_router(
    transcription_service=(
        default_transcription_stack.live_fallback_service
    ),
    smart_turn_service=smart_turn_service,
    streaming_transcription_service=(
        default_transcription_stack.streaming_service
    ),
)

tts_router = create_tts_router(default_tts_service)
tts_stream_router = create_tts_stream_router(
    default_tts_service
)

app.include_router(health_router)
app.include_router(query_router)
app.include_router(llm_router)
app.include_router(artworks_router)
app.include_router(conversation_router)
app.include_router(docent_retrieval_router)
app.include_router(docent_index_router)
app.include_router(docent_embeddings_router)
app.include_router(docent_vector_router)
app.include_router(utterance_router)
app.include_router(trp_router)
app.include_router(turn_detection_router)
app.include_router(turn_buffer_router)
app.include_router(turn_buffer_stream_router)
app.include_router(transcription_router)
app.include_router(audio_stream_router)
app.include_router(tts_router)
app.include_router(tts_stream_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.backend_host,
        port=settings.backend_port,
        log_level="info",
    )
