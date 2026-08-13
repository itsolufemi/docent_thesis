import asyncio
import json
import os
import time

import requests
import websockets
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("QMUL_JUPYTER_TOKEN")

if not TOKEN:
    raise RuntimeError("QMUL_JUPYTER_TOKEN not found")


BASE_HTTP_URL = (
    "https://hub.comp-teach.qmul.ac.uk/"
    "user/ec25326"
)

BASE_WS_URL = (
    "wss://hub.comp-teach.qmul.ac.uk/"
    "user/ec25326"
)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}

WHISPER_HEALTH_URL = (
    "https://hub.comp-teach.qmul.ac.uk/"
    "user/ec25326/proxy/8000/health"
)


def create_terminal():
    response = requests.post(
        f"{BASE_HTTP_URL}/api/terminals",
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()
    terminal_name = data["name"]

    print(
        f"Created QMUL terminal: {terminal_name}"
    )

    return terminal_name


def wait_for_whisper(timeout_seconds=120):
    start = time.perf_counter()

    while time.perf_counter() - start < timeout_seconds:
        try:
            response = requests.get(
                WHISPER_HEALTH_URL,
                headers=HEADERS,
                timeout=5,
            )

            if response.status_code == 200:
                data = response.json()

                if data.get("status") == "ok":
                    elapsed = time.perf_counter() - start

                    print(
                        f"Whisper ready after {elapsed:.2f}s"
                    )

                    return True

        except requests.RequestException:
            pass

        time.sleep(1)

    raise TimeoutError(
        "Whisper service did not become ready in time."
    )


async def main():
    terminal_name = create_terminal()

    ws_url = (
        f"{BASE_WS_URL}/terminals/"
        f"websocket/{terminal_name}"
    )

    async with websockets.connect(
        ws_url,
        additional_headers=HEADERS,
    ) as websocket:

        print("Connected to QMUL terminal.")

        command = (
            "~/msc_project/whisper_server/"
            "start_whisper.sh\n"
        )

        await websocket.send(
            json.dumps([
                "stdin",
                command,
            ])
        )

        print("Start command sent.")

        try:
            while True:
                message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=15,
                )

                data = json.loads(message)

                print(
                    "Terminal message:",
                    data,
                )

                if (
                    isinstance(data, list)
                    and len(data) >= 2
                    and (
                        "Whisper service starting"
                        in str(data[1])
                        or
                        "Whisper service already running"
                        in str(data[1])
                    )
                ):
                    break

        except asyncio.TimeoutError:
            print(
                "No further terminal output received."
            )

    # Terminal command has now been issued.
    # Wait until the actual FastAPI/Whisper service is healthy.
    wait_for_whisper()


asyncio.run(main())