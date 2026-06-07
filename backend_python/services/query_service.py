from services.llm_service import generate_llm_response
from services.prompt_service import build_prompt

def generate_basic_response(text: str) -> str:
    prompt = build_prompt(text)
    return generate_llm_response(prompt)