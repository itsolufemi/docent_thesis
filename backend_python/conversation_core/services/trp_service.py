import json
from time import perf_counter

from config import settings
from conversation_core.schemas.trp_schemas import TRPPrediction
from conversation_core.services.llm_service import generate_llm_response


DEFAULT_TRP_THRESHOLD = 0.70


def build_trp_prompt(
    partial_utterance: str,
    previous_turns: list[str],
) -> str:
    recent_context = "\n".join(previous_turns[-4:])

    return f"""
You are a semantic transition-relevance predictor for spoken conversation.

Determine whether the user's current partial utterance has reached a
possible completion point where another speaker could appropriately respond.

Evaluate grammatical, semantic and pragmatic completeness.

An utterance is probably incomplete when it:
- ends with a conjunction, preposition or unfinished clause;
- clearly projects more speech;
- is only an opening fragment;
- ends with hesitation before completing its apparent meaning.

An utterance is probably complete when it:
- forms a complete question, statement, request, greeting or response;
- could naturally stand as the user's completed conversational turn.

Do not answer the user.
Return only JSON using this exact shape:

{{
  "trp_probability": 0.0,
  "turn_complete": false,
  "reason": "brief reason"
}}

Recent dialogue:
{recent_context or "No previous dialogue."}

Current partial utterance:
{partial_utterance}
""".strip()


def parse_trp_prediction_json(
    raw_response: str,
) -> dict:
    cleaned_response = raw_response.strip()

    if cleaned_response.startswith("```"):
        cleaned_response = cleaned_response.strip("`").strip()

        if cleaned_response.lower().startswith("json"):
            cleaned_response = cleaned_response[4:].strip()

    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError:
        start_index = cleaned_response.find("{")
        end_index = cleaned_response.rfind("}")

        if start_index == -1 or end_index == -1 or end_index <= start_index:
            raise

        json_candidate = cleaned_response[start_index:end_index + 1]

        return json.loads(json_candidate)


def predict_transition_relevance(
    partial_utterance: str,
    previous_turns: list[str] | None = None,
    threshold: float = DEFAULT_TRP_THRESHOLD,
) -> TRPPrediction:
    if not settings.ollama_trp_model:
        raise ValueError(
            "OLLAMA_TRP_MODEL must be configured before making TRP predictions."
        )

    started_at = perf_counter()
    prompt = build_trp_prompt(
        partial_utterance=partial_utterance,
        previous_turns=previous_turns or [],
    )
    raw_response = generate_llm_response(
        prompt=prompt,
        model=settings.ollama_trp_model,
        timeout=20.0,
        options={
            "temperature": 0,
            "num_predict": 80,
        },
    )
    payload = parse_trp_prediction_json(raw_response)
    prediction = TRPPrediction.model_validate(payload)

    prediction.turn_complete = (
        prediction.trp_probability >= threshold
    )
    prediction.prediction_seconds = round(
        perf_counter() - started_at,
        4,
    )

    return prediction
