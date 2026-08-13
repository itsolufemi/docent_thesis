import asyncio
import json
import os
import time

import requests
import websockets
from dotenv import load_dotenv


load_dotenv()


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

STOP_WHISPER_COMMAND = (
    "~/msc_project/whisper_server/"
    "stop_whisper.sh\n"
)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}


# ---------------------------------------------------------------------
# QMUL Jupyter server state
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
            False,
        ),
        "stopped": server.get(
            "stopped",
            False,
        ),
        "pending": server.get(
            "pending",
        ),
        "url": server.get(
            "url",
        ),
        "profile": user_options.get(
            "profile",
        ),
        "profile_display_name": (
            user_options.get(
                "profile_display_name",
            )
        ),
    }


def verify_profile(state):
    if (
        state["profile"] != EXPECTED_PROFILE_ID
        or
        state["profile_display_name"]
        != EXPECTED_PROFILE_NAME
    ):
        raise RuntimeError(
            "Refusing QMUL Whisper shutdown: "
            "wrong Jupyter profile is running. "
            f"Found "
            f"{state['profile_display_name']!r} "
            f"({state['profile']!r}); "
            f"expected "
            f"{EXPECTED_PROFILE_NAME!r} "
            f"({EXPECTED_PROFILE_ID!r})."
        )


# ---------------------------------------------------------------------
# Whisper health
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
            data.get("model") == "large-v3"
        )

    except (
        requests.RequestException,
        ValueError,
    ):
        return False


def wait_for_whisper_stopped(
    timeout_seconds=30
):
    start = time.perf_counter()

    while (
        time.perf_counter() - start
        < timeout_seconds
    ):
        if not whisper_is_healthy():
            elapsed = (
                time.perf_counter()
                - start
            )

            print(
                "Whisper service stopped "
                f"after {elapsed:.2f}s."
            )

            return True

        time.sleep(0.5)

    raise TimeoutError(
        "Whisper service did not stop "
        "within the timeout."
    )


# ---------------------------------------------------------------------
# Terminal management
# ---------------------------------------------------------------------

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


def delete_terminal(
    terminal_name,
    ignore_missing=True,
):
    response = requests.delete(
        (
            f"{USER_SERVER_HTTP_URL}"
            f"/api/terminals/{terminal_name}"
        ),
        headers=HEADERS,
        timeout=30,
    )

    if response.status_code == 204:
        print(
            "QMUL terminal "
            f"{terminal_name} closed."
        )
        return True

    if (
        response.status_code == 404
        and ignore_missing
    ):
        print(
            "QMUL terminal "
            f"{terminal_name} "
            "already absent."
        )
        return True

    raise RuntimeError(
        "Could not delete QMUL terminal "
        f"{terminal_name}: "
        f"{response.status_code} "
        f"{response.text}"
    )


def list_terminals():
    response = requests.get(
        (
            f"{USER_SERVER_HTTP_URL}"
            "/api/terminals"
        ),
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def cleanup_terminals():
    """
    Delete all currently running terminals
    in the verified QMUL Whisper Jupyter
    profile.

    Use this only as part of the dedicated
    Docent/QMUL environment shutdown.
    """

    terminals = list_terminals()

    if not terminals:
        print(
            "No QMUL terminals to clean up."
        )
        return

    for terminal in terminals:
        terminal_name = terminal.get("name")

        if terminal_name is None:
            continue

        delete_terminal(
            terminal_name,
            ignore_missing=True,
        )


# ---------------------------------------------------------------------
# Remote Whisper shutdown
# ---------------------------------------------------------------------

async def stop_whisper_remotely():
    state = get_server_state()

    if not state["exists"]:
        print(
            "QMUL Jupyter server is already "
            "stopped; Whisper cannot be running."
        )
        return True

    if not state["ready"]:
        print(
            "QMUL Jupyter server is not ready."
        )
        return True

    verify_profile(state)

    if not whisper_is_healthy():
        print(
            "Whisper service is already stopped."
        )
        return True

    terminal_name = create_terminal()

    ws_url = (
        f"{USER_SERVER_WS_URL}"
        "/terminals/websocket/"
        f"{terminal_name}"
    )

    try:
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
                    STOP_WHISPER_COMMAND,
                ])
            )

            print(
                "Whisper stop command sent."
            )

            try:
                while True:
                    message = (
                        await asyncio.wait_for(
                            websocket.recv(),
                            timeout=20,
                        )
                    )

                    data = json.loads(message)

                    if (
                        isinstance(data, list)
                        and len(data) >= 2
                    ):
                        output = str(data[1])

                        print(
                            "Terminal:",
                            output.strip(),
                        )

                        if (
                            "Whisper service stopped"
                            in output
                            or
                            "Whisper process is not running"
                            in output
                            or
                            "Whisper PID file not found"
                            in output
                        ):
                            break

            except asyncio.TimeoutError:
                print(
                    "No final stop confirmation "
                    "received from terminal; "
                    "checking health directly."
                )

    finally:
        delete_terminal(
            terminal_name,
            ignore_missing=True,
        )

    wait_for_whisper_stopped()

    return True


# ---------------------------------------------------------------------
# Jupyter server shutdown
# ---------------------------------------------------------------------

def stop_jupyter_server():
    state = get_server_state()

    if not state["exists"]:
        print(
            "QMUL Jupyter server "
            "is already stopped."
        )
        return True

    if state["ready"]:
        verify_profile(state)

    url = (
        f"{HUB_URL}/hub/api/users/"
        f"{USERNAME}/server"
    )

    response = requests.delete(
        url,
        headers=HEADERS,
        timeout=30,
    )

    if response.status_code not in (
        202,
        204,
    ):
        raise RuntimeError(
            "Could not stop QMUL "
            "Jupyter server: "
            f"{response.status_code} "
            f"{response.text}"
        )

    print(
        "QMUL Jupyter server "
        "stop requested."
    )

    return True


def wait_for_jupyter_server_stopped(
    timeout_seconds=180
):
    start = time.perf_counter()

    while (
        time.perf_counter() - start
        < timeout_seconds
    ):
        state = get_server_state()

        if not state["exists"]:
            elapsed = (
                time.perf_counter()
                - start
            )

            print(
                "QMUL Jupyter server stopped "
                f"after {elapsed:.2f}s."
            )

            return True

        print(
            "Waiting for QMUL "
            "Jupyter server to stop..."
        )

        time.sleep(2)

    raise TimeoutError(
        "QMUL Jupyter server "
        "did not stop in time."
    )


# ---------------------------------------------------------------------
# Public shutdown modes
# ---------------------------------------------------------------------

async def shutdown_whisper_only():
    """
    Stop Whisper/Uvicorn but leave the
    QMUL Jupyter server running.
    """

    overall_start = time.perf_counter()

    print()
    print(
        "Stopping QMUL Whisper service..."
    )

    await stop_whisper_remotely()

    elapsed = (
        time.perf_counter()
        - overall_start
    )

    print(
        "Whisper-only shutdown "
        f"complete in {elapsed:.2f}s."
    )

    return True


async def shutdown_qmul_whisper_full():
    """
    Stop Whisper, clean up terminals,
    then stop the complete QMUL
    Jupyter user server.
    """

    overall_start = time.perf_counter()

    print()
    print(
        "Starting full QMUL "
        "Whisper shutdown..."
    )

    state = get_server_state()

    if not state["exists"]:
        print(
            "QMUL Jupyter server "
            "is already stopped."
        )
        return True

    if state["ready"]:
        verify_profile(state)

    # 1. Stop detached Uvicorn/Whisper.
    await stop_whisper_remotely()

    # 2. Remove any remaining terminals.
    #
    # This is appropriate for the dedicated
    # NLP/Docent instance. If you later use
    # this same profile interactively while
    # Docent is running, we may want to
    # narrow this cleanup policy.
    cleanup_terminals()

    # 3. Stop the entire Jupyter user server.
    stop_jupyter_server()

    # 4. Wait until JupyterHub confirms
    #    that the server has disappeared.
    wait_for_jupyter_server_stopped()

    elapsed = (
        time.perf_counter()
        - overall_start
    )

    print(
        "Full QMUL Whisper shutdown "
        f"complete in {elapsed:.2f}s."
    )

    return True


# ---------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------

if __name__ == "__main__":
    # Default standalone behaviour:
    # shut down the full QMUL Whisper stack.
    asyncio.run(
        shutdown_qmul_whisper_full()
    )