from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from conversation_core.schemas.tts_schemas import (
    TextToSpeechRequest,
)
from conversation_core.services.tts_service import (
    TextToSpeechService,
)


def create_tts_router(
    tts_service: TextToSpeechService,
) -> APIRouter:
    router = APIRouter()
    active_tts_service = tts_service

    @router.post(
        "/api/tts/synthesise",
        response_class=Response,
    )
    def synthesise_speech(
        request: TextToSpeechRequest,
    ) -> Response:
        try:
            result = active_tts_service.synthesise(
                request.text,
                voice_name=request.voice_name,
                language_code=request.language_code,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"{active_tts_service.provider_name} "
                    "text-to-speech synthesis failed: "
                    f"{error}"
                ),
            ) from error

        return Response(
            content=result.audio,
            media_type="audio/wav",
            headers={
                "X-TTS-Provider": result.provider_name,
                "X-TTS-Voice": result.voice_name,
                "X-TTS-Language": (
                    result.language_code
                ),
                "X-TTS-Sample-Rate": str(
                    result.sample_rate
                ),
                "X-TTS-Characters": str(
                    result.character_count
                ),
                "X-TTS-Generation-Seconds": (
                    f"{result.generation_seconds:.4f}"
                ),
            },
        )

    return router
