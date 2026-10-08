import asyncio
import json
import os
import time

import numpy as np
import soundfile as sf
import websockets
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("QMUL_JUPYTER_TOKEN")

WS_URL = (
    "wss://hub.comp-teach.qmul.ac.uk/"
    "user/ec25326/proxy/8000/ws/transcribe"
)

AUDIO_PATH = r"./test_6s.wav"

SAMPLE_RATE = 16000
CHUNK_MS = 20

CHUNK_SAMPLES = int(
    SAMPLE_RATE * CHUNK_MS / 1000
)


async def main():

    audio, sample_rate = sf.read(
        AUDIO_PATH,
        dtype="int16"
    )

    if sample_rate != SAMPLE_RATE:
        raise ValueError(
            f"Expected 16000 Hz, got {sample_rate}"
        )

    if audio.ndim > 1:
        audio = audio[:, 0]

    headers = {
        "Authorization": f"Bearer {TOKEN}"
    }

    async with websockets.connect(
        WS_URL,
        additional_headers=headers
    ) as websocket:

        print("WebSocket connected")

        # Simulate live microphone streaming
        for start in range(
            0,
            len(audio),
            CHUNK_SAMPLES
        ):
            chunk = audio[
                start:start + CHUNK_SAMPLES
            ]

            await websocket.send(
                chunk.tobytes()
            )

            # Real microphone audio would naturally
            # arrive every ~20ms
            await asyncio.sleep(
                CHUNK_MS / 1000
            )

        print("Audio streaming complete")

        finalization_start = time.perf_counter()

        await websocket.send(
            json.dumps({
                "type": "finalize"
            })
        )

        response = await websocket.recv()

        post_finalize_seconds = (
            time.perf_counter()
            - finalization_start
        )

        result = json.loads(response)

        print()
        print(json.dumps(
            result,
            indent=2
        ))

        print()
        print(
            "Finalize → transcript:",
            f"{post_finalize_seconds:.3f}s"
        )


asyncio.run(main())