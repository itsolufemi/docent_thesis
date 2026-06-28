from memory.session_store import (
    add_dialogue_turn,
    get_recent_dialogue_history,
    get_session
)

from schemas.context_schemas import QueryDebugInfo
from services.llm_service import generate_llm_response
from services.prompt_service import build_prompt
from services.artwork_service import get_painting_by_index

def generate_basic_response(
    text: str, 
    painting_index: int | None = None, 
    session_id: str | None = None,
    include_debug: bool = False
    )-> tuple[str, int | None, QueryDebugInfo | None]:
    resolved_painting_index = painting_index
    context_source = "no_artwork_context"
    dialogue_history = []

    session_state = None

    if session_id is not None:
        session_state = get_session(session_id)

        if session_state is None:
            context_source = "session_not_found"
        else:
            dialogue_history = get_recent_dialogue_history(session_id)
    
    if resolved_painting_index is not None:
        context_source = "direct_painting_index"
    
    if resolved_painting_index is None and session_state is not None:
        resolved_painting_index = session_state.current_painting_index

        if resolved_painting_index is not None:
            context_source = "session_current_painting"

    artwork = None

    if resolved_painting_index is not None:
        artwork = get_painting_by_index(resolved_painting_index)

        if artwork is None:
            context_source = "painting_index_not_found"
    
    prompt = build_prompt(
        user_input=text,
        artwork=artwork,
        dialogue_history=dialogue_history
    )
    
    response = generate_llm_response(prompt)

    if session_state is not None:
        add_dialogue_turn(
            session_id=session_state.session_id,
            role="user",
            content=text,
        )

        add_dialogue_turn(
            session_id=session_state.session_id,
            role="assistant",
            content=response,
        )

    final_painting_index = (
        artwork.painting_index
        if artwork is not None
        else None
    )

    debug_info = None


    if include_debug:
        debug_info = QueryDebugInfo(
            resolved_painting_index=final_painting_index,
            context_source=context_source,
            artwork_context_used=artwork is not None,
            dialogue_turns_used=len(dialogue_history),
            prompt=prompt,
        )

    return response, final_painting_index, debug_info

