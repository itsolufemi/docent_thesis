from services.llm_service import generate_llm_response
from services.prompt_service import build_prompt
from services.artwork_service import get_painting_by_index

def generate_basic_response(
        text: str, 
        painting_index: int | None = None ) -> tuple[str, int | None]:
    
    artwork = None

    if painting_index is not None:
        artwork = get_painting_by_index(painting_index)

    prompt = build_prompt(text, artwork)
    response = generate_llm_response(prompt)

    resolved_painting_index = artwork.painting_index if artwork is not None else None

    return response, resolved_painting_index