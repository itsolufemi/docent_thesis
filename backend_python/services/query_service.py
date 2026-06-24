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

    if resolved_painting_index is None and session_id is not None:
        session_state = get_session(session_id)

        if session_state is not None:
            resolved_painting_index = session_state.current_painting_index
    
    artwork = None

    if resolved_painting_index is not None:
        artwork = get_painting_by_index(resolved_painting_index)

    prompt = build_prompt(text, artwork)
    response = generate_llm_response(prompt)

    result_painting_index = (
        artwork.painting_index
        if artwork is not None
        else None           
    )

    return response, result_painting_index