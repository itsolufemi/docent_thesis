from services.llm_service import generate_llm_response

def generate_basic_response(text: str) -> str:
    prompt = f"""
you are docent, a conversational ai museum guide.
the user said: {text}

respond briefly and naturally, as if speaking aloud to a visitor.
"""
    return generate_llm_response(prompt)