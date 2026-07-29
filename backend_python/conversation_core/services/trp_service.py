import json
from time import perf_counter

import httpx

from config import settings
from conversation_core.schemas.trp_schemas import TRPPrediction


DEFAULT_TRP_THRESHOLD = 0.70
TRP_REQUEST_TIMEOUT_SECONDS = 20.0
TRP_REQUEST_OPTIONS = {
    "temperature": 0,
    "num_predict": 160,
}
TRP_RESPONSE_FORMAT = {
    "type": "object",
    "properties": {
        "trp_probability": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "turn_complete": {
            "type": "boolean",
        },
        "reason": {
            "type": "string",
        },
    },
    "required": [
        "trp_probability",
        "turn_complete",
        "reason",
    ],
}


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


def request_streaming_trp_prediction(
    prompt: str,
) -> TRPPrediction:
    request_payload = {
        "model": settings.ollama_trp_model,
        "prompt": prompt,
        "stream": True,
        "think": False,
        "format": TRP_RESPONSE_FORMAT,
        "options": TRP_REQUEST_OPTIONS,
    }
    accumulated_response = ""

    with httpx.stream(
        method="POST",
        url=(
            f"{settings.ollama_base_url}"
            "/api/generate"
        ),
        json=request_payload,
        timeout=TRP_REQUEST_TIMEOUT_SECONDS,
    ) as response:
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue

            chunk = json.loads(line)

            if chunk.get("error"):
                raise RuntimeError(
                    "Ollama TRP stream failed: "
                    f"{chunk['error']}"
                )

            accumulated_response += chunk.get(
                "response",
                "",
            )

            if accumulated_response:
                try:
                    prediction = (
                        TRPPrediction.model_validate(
                            parse_trp_prediction_json(
                                accumulated_response
                            )
                        )
                    )
                except (
                    json.JSONDecodeError,
                    ValueError,
                ):
                    pass
                else:
                    response.close()
                    return prediction

            if chunk.get("done"):
                break

    raise ValueError(
        "The Ollama TRP stream completed without "
        "producing valid structured JSON."
    )


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
    prediction = request_streaming_trp_prediction(
        prompt=prompt,
    )

    prediction.turn_complete = (
        prediction.trp_probability >= threshold
    )
    prediction.prediction_seconds = round(
        perf_counter() - started_at,
        4,
    )

    return prediction
