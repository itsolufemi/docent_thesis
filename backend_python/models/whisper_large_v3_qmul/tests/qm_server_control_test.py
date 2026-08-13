import os
import time
import requests

from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("QMUL_JUPYTER_TOKEN")

if not TOKEN:
    raise RuntimeError("QMUL_JUPYTER_TOKEN not found")


HUB_URL = "https://hub.comp-teach.qmul.ac.uk"
USERNAME = "ec25326"

EXPECTED_PROFILE_ID = "60995eaedf70d00f"
EXPECTED_PROFILE_NAME = "Neural Networks and NLP"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}


def get_server_state():
    url = f"{HUB_URL}/hub/api/users/{USERNAME}"

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
            "profile": None,
            "profile_display_name": None,
        }

    user_options = server.get("user_options", {})

    return {
        "exists": True,
        "ready": server.get("ready", False),
        "stopped": server.get("stopped", False),
        "pending": server.get("pending"),
        "url": server.get("url"),
        "profile": user_options.get("profile"),
        "profile_display_name": user_options.get(
            "profile_display_name"
        ),
    }


def start_server():
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

    print("Start status:", response.status_code)
    print("Response:", response.text)

    return response


def wait_for_server(timeout_seconds=180):
    start = time.perf_counter()

    while (
        time.perf_counter() - start
        < timeout_seconds
    ):
        state = get_server_state()

        print("Server state:")
        print(state)

        if state["ready"]:
            print("QMUL Jupyter server is ready.")
            return True

        time.sleep(2)

    raise TimeoutError(
        "QMUL Jupyter server did not become ready in time."
    )


if __name__ == "__main__":
    state = get_server_state()

    print("Current state:")
    print(state)

    if state["ready"]:
        if (
            state["profile"] != EXPECTED_PROFILE_ID
            or state["profile_display_name"]
            != EXPECTED_PROFILE_NAME
        ):
            raise RuntimeError(
                "Wrong QMUL Jupyter profile is running. "
                f"Found "
                f"{state['profile_display_name']!r} "
                f"({state['profile']!r}); "
                f"expected "
                f"{EXPECTED_PROFILE_NAME!r} "
                f"({EXPECTED_PROFILE_ID!r})."
            )

        print("Correct QMUL profile confirmed.")

    else:
        response = start_server()

        if response.status_code not in (201, 202):
            raise RuntimeError(
                "Could not start QMUL server: "
                f"{response.status_code} "
                f"{response.text}"
            )

        wait_for_server()

        state = get_server_state()

        print("Started server state:")
        print(state)

        if (
            state["profile"] != EXPECTED_PROFILE_ID
            or state["profile_display_name"]
            != EXPECTED_PROFILE_NAME
        ):
            raise RuntimeError(
                "QMUL started the wrong profile. "
                f"Found "
                f"{state['profile_display_name']!r} "
                f"({state['profile']!r})."
            )

        print(
            "Correct QMUL profile "
            "started successfully."
        )