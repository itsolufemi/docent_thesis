from __future__ import annotations

from io import BytesIO
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
import numpy as np
import soundfile as sf

from app.schemas import SynthesisRequest
from app.services.kokoro_service import (
    KOKORO_SAMPLE_RATE,
    kokoro_service,
)


app = FastAPI(
    title="Docent Kokoro TTS Service",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "kokoro-tts",
    }


@app.post("/synthesise")
def synthesise(
    request: SynthesisRequest,
) -> Response:
    started_at = perf_counter()

    try:
        chunks = list(
            kokoro_service.synthesise(
                request.text,
                voice=request.voice,
                speed=request.speed,
            )
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Kokoro synthesis failed: "
                f"{error}"
            ),
        ) from error

    if not chunks:
        raise HTTPException(
            status_code=500,
            detail="Kokoro returned no audio.",
        )

    combined_audio = np.concatenate(
        [chunk.audio for chunk in chunks]
    ).astype(
        np.float32,
        copy=False,
    )

    wav_buffer = BytesIO()

    sf.write(
        wav_buffer,
        combined_audio,
        KOKORO_SAMPLE_RATE,
        format="WAV",
        subtype="PCM_16",
    )

    elapsed_seconds = perf_counter() - started_at

    return Response(
        content=wav_buffer.getvalue(),
        media_type="audio/wav",
        headers={
            "X-TTS-Sample-Rate": str(
                KOKORO_SAMPLE_RATE
            ),
            "X-TTS-Chunk-Count": str(
                len(chunks)
            ),
            "X-TTS-Generation-Seconds": (
                f"{elapsed_seconds:.4f}"
            ),
        },
    )
