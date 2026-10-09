from __future__ import annotations

import atexit

import httpx

from config import settings


ollama_http_client = httpx.Client(
    base_url=settings.ollama_base_url.rstrip("/"),
    timeout=httpx.Timeout(
        timeout=120.0,
        connect=15.0,
    ),
    limits=httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=60.0,
    ),
)


def close_ollama_http_client() -> None:
    ollama_http_client.close()


# The client is process-scoped and may be shared by several FastAPI apps.
# Closing it from one app's lifespan would invalidate the other apps, so it is
# released only when the Python interpreter exits.
atexit.register(close_ollama_http_client)
