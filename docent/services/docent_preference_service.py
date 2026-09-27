from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from collections.abc import Iterator

from docent.config.preference_config import (
    INTEREST_SIGNAL_MULTIPLIERS,
    INTEREST_UPDATE_RATE,
)
from docent.schemas.preference_schemas import (
    DocentPreferenceEvidence,
    DocentPreferenceState,
)
from docent.services.docent_preference_store import (
    DocentPreferenceStore,
    docent_preference_store,
)


_active_preference_state: ContextVar[
    DocentPreferenceState | None
] = ContextVar(
    "active_docent_preference_state",
    default=None,
)


def apply_docent_preference_evidence(
    state: DocentPreferenceState,
    evidence: DocentPreferenceEvidence,
) -> DocentPreferenceState:
    if evidence.is_empty():
        return state.model_copy(deep=True)

    interests = dict(state.interests)

    for signal in evidence.interest_signals:
        interests[signal.category] += (
            INTEREST_UPDATE_RATE
            * INTEREST_SIGNAL_MULTIPLIERS[signal.strength]
        )

    total = sum(interests.values())
    normalised = {
        category: value / total
        for category, value in interests.items()
    }
    technical_depth = (
        state.technical_depth
        if evidence.technical_depth_signal == "unchanged"
        else evidence.technical_depth_signal
    )
    verbosity = (
        state.verbosity
        if evidence.verbosity_signal == "unchanged"
        else evidence.verbosity_signal
    )

    return DocentPreferenceState(
        interests=normalised,
        technical_depth=technical_depth,
        verbosity=verbosity,
    )


def update_docent_preferences(
    conversation_id: str,
    evidence: DocentPreferenceEvidence,
    *,
    store: DocentPreferenceStore = docent_preference_store,
) -> tuple[DocentPreferenceState, DocentPreferenceState]:
    return store.update(
        conversation_id,
        lambda current: apply_docent_preference_evidence(
            current,
            evidence,
        ),
    )


def get_active_docent_preference_state() -> (
    DocentPreferenceState | None
):
    state = _active_preference_state.get()
    return (
        state.model_copy(deep=True)
        if state is not None
        else None
    )


@contextmanager
def use_docent_preference_state(
    state: DocentPreferenceState,
) -> Iterator[None]:
    token: Token = _active_preference_state.set(
        state.model_copy(deep=True)
    )

    try:
        yield
    finally:
        _active_preference_state.reset(token)
