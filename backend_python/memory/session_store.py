from uuid import uuid4

from schemas.session_schemas import SessionState

sessions: dict[str, SessionState] = {}

def create_session() -> SessionState:
    session_id = str(uuid4())
    
    state = SessionState(
        session_id = session_id,
    )

    sessions[session_id] = state
    return state

def get_session(session_id:str) -> SessionState | None:
    return sessions.get(session_id)

def set_current_painting(
        session_id:str,
        painting_index: int,
) -> SessionState | None:
    state = get_session(session_id)

    if state is None:
        return None
    
    if state.current_painting_index is not None:
        state.previous_painting_index = state.current_painting_index

        if state.current_painting_index not in state.visited_painting_indexes:
            state.visited_painting_indexes.append(state.current_painting_index)

    state.current_painting_index = painting_index

    sessions[session_id] = state
    return state
