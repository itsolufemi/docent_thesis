from memory.session_store import (
    add_dialogue_turn,
    get_recent_dialogue_history,
    get_session
)

from services.llm_service import generate_llm_response
from services.prompt_service import build_prompt
from services.artwork_service import get_painting_by_index
from memory.session_store import get_session

def generate_basic_response(
    text: str, 
    painting_index: int | None = None, 
    session_id: str | None = None,
    )-> tuple[str, int | None]:

    resolved_painting_index = painting_index
    dialogue_history = []

    if session_id is not None:
        dialogue_history = get_recent_dialogue_history(session_id)

    if resolved_painting_index is None and session_id is not None:
        session_state = get_session(session_id)

        if session_state is not None:
            resolved_painting_index = session_state.current_painting_index
    
    artwork = None

    if resolved_painting_index is not None:
        artwork = get_painting_by_index(resolved_painting_index)

    prompt = build_prompt(
        user_input = text, 
        artwork = artwork,
        dialogue_history = dialogue_history
    )

    response = generate_llm_response(prompt)

    if session_id is not None and get_session(session_id) is not None:
        add_dialogue_turn(
            session_id=session_id,
            role="user",
            content=text
        )

        add_dialogue_turn(
            session_id=session_id,
            role="assistant",
            content=response
        )
    
    final_painting_index = (
        artwork.painting_index
        if artwork is not None
        else None           
    )

    return response, final_painting_index

