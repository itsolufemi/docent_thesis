from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from docent.schemas.discovery_schemas import PreparedDiscoveryState


PREPARED_DISCOVERY_MAX_AGE_SECONDS = 30 * 60


class DocentDiscoveryStore:
    """Conversation-scoped scratch state for prepared discoveries."""

    def __init__(self) -> None:
        self._states: dict[str, PreparedDiscoveryState] = {}
        self._lock = RLock()

    def get(
        self,
        conversation_id: str | None,
    ) -> PreparedDiscoveryState | None:
        if conversation_id is None:
            return None

        with self._lock:
            state = self._states.get(conversation_id)
            if state is None:
                return None

            age = (
                datetime.now(timezone.utc) - state.created_at
            ).total_seconds()
            if age > PREPARED_DISCOVERY_MAX_AGE_SECONDS:
                self._states.pop(conversation_id, None)
                return None

            return state.model_copy(deep=True)

    def set(
        self,
        conversation_id: str,
        state: PreparedDiscoveryState,
    ) -> PreparedDiscoveryState:
        with self._lock:
            stored = state.model_copy(
                update={"conversation_id": conversation_id},
                deep=True,
            )
            self._states[conversation_id] = stored
            return stored.model_copy(deep=True)

    def mark_surfaced(
        self,
        conversation_id: str,
        reference: str,
    ) -> PreparedDiscoveryState | None:
        with self._lock:
            state = self._states.get(conversation_id)
            if state is None:
                return None

            state.surfaced_reference = reference
            self._states[conversation_id] = state
            return state.model_copy(deep=True)

    def delete(self, conversation_id: str) -> None:
        with self._lock:
            self._states.pop(conversation_id, None)

    def clear(self) -> None:
        with self._lock:
            self._states.clear()


docent_discovery_store = DocentDiscoveryStore()


def mark_prepared_discovery_surfaced_from_response(
    conversation_id: str,
    response: str,
    *,
    store: DocentDiscoveryStore = docent_discovery_store,
) -> PreparedDiscoveryState | None:
    state = store.get(conversation_id)
    if state is None:
        return None

    continuation = response
    if (
        state.source_response_text
        and response.startswith(state.source_response_text)
    ):
        continuation = response[len(state.source_response_text):]

    normalised_continuation = continuation.casefold()
    for candidate in [
        *state.current_artwork_candidates,
        *state.collection_candidates,
    ]:
        title = str(candidate.get("title") or "").strip()
        reference = str(candidate.get("reference") or "").strip()
        if title and title.casefold() in normalised_continuation and reference:
            return store.mark_surfaced(conversation_id, reference)

    return state
