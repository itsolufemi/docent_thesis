from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
)
from starlette.concurrency import run_in_threadpool

from conversation_core.schemas.transcription_schemas import (
    TranscriptionResponse,
)
from conversation_core.services.transcription_service import (
    TranscriptionService,
    default_transcription_service,
)


MAX_AUDIO_SIZE_BYTES = 15 * 1024 * 1024

PERMITTED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
}


def create_transcription_router(
    transcription_service: TranscriptionService | None = None,
) -> APIRouter:
    router = APIRouter()
    active_service = (
        transcription_service
        or default_transcription_service
    )

    @router.post(
        "/api/transcription",
        response_model=TranscriptionResponse,
    )
    async def transcribe_audio(
        audio: UploadFile = File(...),
    ) -> TranscriptionResponse:
        temporary_path: Path | None = None

        try:
            if (
                audio.content_type
                and audio.content_type not in PERMITTED_AUDIO_TYPES
            ):
                raise HTTPException(
                    status_code=415,
                    detail=(
                        "Unsupported audio type: "
                        f"{audio.content_type}"
                    ),
                )

            audio_bytes = await audio.read()

            if not audio_bytes:
                raise HTTPException(
                    status_code=400,
                    detail="The uploaded audio file is empty.",
                )

            if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="The uploaded audio file is too large.",
                )

            filename = audio.filename or "audio.wav"
            suffix = Path(filename).suffix or ".wav"

            with NamedTemporaryFile(
                suffix=suffix,
                delete=False,
            ) as temporary_file:
                temporary_file.write(audio_bytes)
                temporary_path = Path(temporary_file.name)

            return await run_in_threadpool(
                active_service.transcribe_file,
                temporary_path,
            )

        except HTTPException:
            raise

        except FileNotFoundError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error

        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error

        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=(
                    "The audio could not be transcribed: "
                    f"{error}"
                ),
            ) from error

        finally:
            await audio.close()

            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()

    return router
