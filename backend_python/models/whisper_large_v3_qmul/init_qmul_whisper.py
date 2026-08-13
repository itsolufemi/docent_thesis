import asyncio
import json
import os
import time
from pathlib import Path

import requests
import websockets
from dotenv import load_dotenv


load_dotenv(
    Path(__file__).with_name(".env")
)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

TOKEN = os.getenv("QMUL_JUPYTER_TOKEN")

if not TOKEN:
    raise RuntimeError("QMUL_JUPYTER_TOKEN not found")


HUB_URL = "https://hub.comp-teach.qmul.ac.uk"
USERNAME = "ec25326"

EXPECTED_PROFILE_ID = "60995eaedf70d00f"
EXPECTED_PROFILE_NAME = "Neural Networks and NLP"

USER_SERVER_HTTP_URL = (
    f"{HUB_URL}/user/{USERNAME}"
)

USER_SERVER_WS_URL = (
    f"wss://hub.comp-teach.qmul.ac.uk/"
    f"user/{USERNAME}"
)

WHISPER_HEALTH_URL = (
    f"{USER_SERVER_HTTP_URL}/proxy/8000/health"
)

START_WHISPER_COMMAND = (
    "~/msc_project/whisper_server/"
    "start_whisper.sh\n"
)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}


# ---------------------------------------------------------------------
# QMUL Jupyter server
# ---------------------------------------------------------------------

def get_server_state():
    url = (
        f"{HUB_URL}/hub/api/users/"
        f"{USERNAME}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()
    server = data.get("servers", {}).get("")

    if not server:
        return {
            "exists": False,
            "ready": False,
            "stopped": True,
            "pending": None,
            "url": None,
            "profile": None,
            "profile_display_name": None,
        }

    user_options = server.get(
        "user_options",
        {}
    )

    return {
        "exists": True,
        "ready": server.get(
            "ready",
            False
        ),
        "stopped": server.get(
            "stopped",
            False
        ),
        "pending": server.get(
            "pending"
        ),
        "url": server.get(
            "url"
        ),
        "profile": user_options.get(
            "profile"
        ),
        "profile_display_name": (
            user_options.get(
                "profile_display_name"
            )
        ),
    }


def verify_profile(state):
    if (
        state["profile"]
        != EXPECTED_PROFILE_ID
        or
        state["profile_display_name"]
        != EXPECTED_PROFILE_NAME
    ):
        raise RuntimeError(
            "Wrong QMUL Jupyter profile. "
            f"Found "
            f"{state['profile_display_name']!r} "
            f"({state['profile']!r}); "
            f"expected "
            f"{EXPECTED_PROFILE_NAME!r} "
            f"({EXPECTED_PROFILE_ID!r})."
        )


def start_jupyter_server():
    url = (
        f"{HUB_URL}/hub/api/users/"
        f"{USERNAME}/server"
    )

    response = requests.post(
        url,
        headers=HEADERS,
        json={
            "profile": EXPECTED_PROFILE_ID
        },
        timeout=30,
    )

    if response.status_code not in (
        201,
        202,
    ):
        raise RuntimeError(
            "Could not start QMUL "
            "Jupyter server: "
            f"{response.status_code} "
            f"{response.text}"
        )

    print(
        "QMUL Jupyter server "
        "start requested."
    )


def wait_for_jupyter_server(
    timeout_seconds=180
):
    start = time.perf_counter()

    while (
        time.perf_counter() - start
        < timeout_seconds
    ):
        state = get_server_state()

        if state["ready"]:
            verify_profile(state)

            elapsed = (
                time.perf_counter()
                - start
            )

            print(
                "QMUL Jupyter server "
                f"ready after "
                f"{elapsed:.2f}s."
            )

            return state

        print(
            "Waiting for QMUL "
            f"Jupyter server... "
            f"pending={state['pending']}"
        )

        time.sleep(2)

    raise TimeoutError(
        "QMUL Jupyter server "
        "did not become ready."
    )


def ensure_jupyter_server_ready():
    state = get_server_state()

    if state["ready"]:
        verify_profile(state)

        print(
            "Correct QMUL Jupyter "
            "profile already running."
        )

        return state

    print(
        "QMUL Jupyter server "
        "is not running."
    )

    start_jupyter_server()

    return wait_for_jupyter_server()


# ---------------------------------------------------------------------
# Whisper service
# ---------------------------------------------------------------------

def whisper_is_healthy():
    try:
        response = requests.get(
            WHISPER_HEALTH_URL,
            headers=HEADERS,
            timeout=5,
        )

        if response.status_code != 200:
            return False

        data = response.json()

        return (
            data.get("status") == "ok"
            and
            data.get("model")
            == "large-v3"
        )

    except (
        requests.RequestException,
        ValueError,
    ):
        return False


def create_terminal():
    response = requests.post(
        (
            f"{USER_SERVER_HTTP_URL}"
            "/api/terminals"
        ),
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    terminal_name = (
        response.json()["name"]
    )

    print(
        "Created QMUL terminal: "
        f"{terminal_name}"
    )

    return terminal_name


async def start_whisper_remotely():
    terminal_name = create_terminal()

    ws_url = (
        f"{USER_SERVER_WS_URL}"
        "/terminals/websocket/"
        f"{terminal_name}"
    )

    async with websockets.connect(
        ws_url,
        additional_headers=HEADERS,
    ) as websocket:

        print(
            "Connected to QMUL terminal."
        )

        await websocket.send(
            json.dumps([
                "stdin",
                START_WHISPER_COMMAND,
            ])
        )

        print(
            "Whisper start command sent."
        )

        try:
            while True:
                message = (
                    await asyncio.wait_for(
                        websocket.recv(),
                        timeout=15,
                    )
                )

                data = json.loads(message)

                if (
                    isinstance(data, list)
                    and len(data) >= 2
                ):
                    output = str(data[1])

                    if (
                        "Whisper service starting"
                        in output
                    ):
                        print(
                            "Whisper service "
                            "is starting."
                        )
                        return

                    if (
                        "Whisper service "
                        "already running"
                        in output
                    ):
                        print(
                            "Whisper service "
                            "already running."
                        )
                        return

        except asyncio.TimeoutError:
            print(
                "No confirmation received "
                "from remote terminal."
            )
            
        finally:
            delete_terminal(terminal_name)


def wait_for_whisper(
    timeout_seconds=120
):
    start = time.perf_counter()

    while (
        time.perf_counter() - start
        < timeout_seconds
    ):
        if whisper_is_healthy():
            elapsed = (
                time.perf_counter()
                - start
            )

            print(
                "Whisper large-v3 ready "
                f"after {elapsed:.2f}s."
            )

            return True

        time.sleep(1)

    raise TimeoutError(
        "Whisper service did not "
        "become ready in time."
    )

def delete_terminal(terminal_name):
    response = requests.delete(
        (
            f"{USER_SERVER_HTTP_URL}"
            f"/api/terminals/{terminal_name}"
        ),
        headers=HEADERS,
        timeout=30,
    )

    if response.status_code not in (204, 404):
        raise RuntimeError(
            "Could not delete QMUL terminal: "
            f"{response.status_code} {response.text}"
        )

    print(
        f"QMUL terminal {terminal_name} closed."
    )


# ---------------------------------------------------------------------
# Full startup
# ---------------------------------------------------------------------

async def ensure_qmul_whisper_ready():
    overall_start = time.perf_counter()

    print()
    print(
        "Initialising QMUL Whisper..."
    )

    # 1. Ensure the correct GPU/Jupyter
    #    environment exists.
    ensure_jupyter_server_ready()

    # 2. Avoid creating a terminal if
    #    Whisper is already available.
    if whisper_is_healthy():
        print(
            "Whisper large-v3 "
            "already ready."
        )

    else:
        print(
            "Whisper service "
            "is not running."
        )

        # 3. Launch Uvicorn/Whisper
        #    inside the QMUL environment.
        await start_whisper_remotely()

        # 4. Wait for model loading
        #    and warm-up to complete.
        wait_for_whisper()

    elapsed = (
        time.perf_counter()
        - overall_start
    )

    print(
        "QMUL Whisper initialisation "
        f"complete in {elapsed:.2f}s."
    )

    return True


# ---------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(
        ensure_qmul_whisper_ready()
    )
