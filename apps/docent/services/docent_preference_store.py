from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from apps.docent.schemas.preference_schemas import DocentPreferenceState


PreferenceUpdater = Callable[
    [DocentPreferenceState],
    DocentPreferenceState,
]


class DocentPreferenceStore:
    """Session-local, in-memory Docent preference state."""

    def __init__(self) -> None:
        self._states: dict[str, DocentPreferenceState] = {}
        self._lock = RLock()

    def get(self, conversation_id: str | None) -> DocentPreferenceState:
        with self._lock:
            state = (
                self._states.get(conversation_id)
                if conversation_id is not None
                else None
            )
            return (
                state.model_copy(deep=True)
                if state is not None
                else DocentPreferenceState()
            )

    def set(
        self,
        conversation_id: str,
        state: DocentPreferenceState,
    ) -> DocentPreferenceState:
        with self._lock:
            stored = state.model_copy(deep=True)
            self._states[conversation_id] = stored
            return stored.model_copy(deep=True)

    def update(
        self,
        conversation_id: str,
        updater: PreferenceUpdater,
    ) -> tuple[DocentPreferenceState, DocentPreferenceState]:
        with self._lock:
            current = self._states.get(
                conversation_id,
                DocentPreferenceState(),
            ).model_copy(deep=True)
            updated = updater(current.model_copy(deep=True))
            self._states[conversation_id] = updated.model_copy(deep=True)
            return current, updated.model_copy(deep=True)

    def delete(self, conversation_id: str) -> None:
        with self._lock:
            self._states.pop(conversation_id, None)

    def clear(self) -> None:
        with self._lock:
            self._states.clear()


docent_preference_store = DocentPreferenceStore()
