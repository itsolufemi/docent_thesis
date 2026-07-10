import json
import re

from conversation_core.schemas.utterance_route_schemas import UtteranceRoute
from conversation_core.services.llm_service import generate_llm_response


VALID_ROUTE_TYPES = {
    "noise",
    "response_request",
    "call_to_action",
    "interruption",
}

def is_non_linguistic_noise(
    text: str,
) -> bool:
    cleaned_text = text.strip()

    if not cleaned_text:
        return True

    word_tokens = re.findall(r"[a-zA-Z]+", cleaned_text)

    if not word_tokens:
        return True

    return False


def build_utterance_route_prompt(
    text: str,
) -> str:
    return f"""
You are a conversation-routing classifier for a general voice-led AI system.

Your task is to classify the user's utterance into exactly one route type.

Route types:

1. noise
Use this when the input should not be treated as meaningful conversational input.
This includes empty input, meaningless symbols, numbers without words, accidental transcription, background speech, or text that does not contain a meaningful linguistic utterance.
For example: "&5", "!!!", "...", "123", or random non-word fragments should be classified as noise.

2. response_request
Use this when the user is asking for a verbal response.
This includes questions, greetings, acknowledgements, follow-up questions, requests for explanation, and normal conversational turns.
Most meaningful utterances should default to this route unless they clearly require another route.

3. call_to_action
Use this only when the user is asking the system to perform an explicit user-facing operation that is supported by an available tool/action.
If no available tool/action is provided, do not classify ordinary operational language as call_to_action. Treat it as response_request unless it is clearly an interruption.

4. interruption
Use this when the user is stopping, pausing, cutting into, or redirecting the system's current speaking or acting turn.
Examples include "stop", "wait", "pause", "hold on", or "no, that's not what I meant".

Important distinction:
- A response_request may still cause internal state updates later.
- A call_to_action means the user's main request is a user-facing operation.
- Default to response_request when the input contains meaningful language but the exact intent is uncertain.
- Do not default to response_request for non-linguistic symbols, numbers, or junk input.
- Do not classify something as call_to_action merely because the user wants an answer.
- Do not invent domain-specific route types.

User utterance:
{text}

Return only a single JSON object.
Do not include markdown.
Do not include comments.
Do not include explanatory text outside the JSON object.

The JSON object must use this exact shape:
{{
  "route_type": "noise | response_request | call_to_action | interruption",
  "is_relevant": true,
  "should_ignore": false,
  "confidence": 0.0,
  "reason": "brief explanation"
}}
""".strip()


def parse_utterance_route_json(
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
def build_fallback_route(
    reason: str,
) -> UtteranceRoute:
    return UtteranceRoute(
        route_type="response_request",
        is_relevant=True,
        should_ignore=False,
        confidence=0.4,
        reason=reason,
    )


def normalise_route_payload(
    payload: dict,
) -> UtteranceRoute:
    route_type = payload.get("route_type")

    if route_type not in VALID_ROUTE_TYPES:
        return build_fallback_route(
            reason="The LLM returned an invalid route type, so the utterance was treated as a response request.",
        )

    is_relevant = bool(payload.get("is_relevant", route_type != "noise"))
    should_ignore = bool(payload.get("should_ignore", route_type == "noise"))

    if route_type == "noise":
        is_relevant = False
        should_ignore = True

    confidence = payload.get("confidence", 0.5)

    try:
        confidence = float(confidence)
    except TypeError:
        confidence = 0.5
    except ValueError:
        confidence = 0.5

    confidence = max(0.0, min(confidence, 1.0))

    reason = str(payload.get("reason", "No reason provided."))

    return UtteranceRoute(
        route_type=route_type,
        is_relevant=is_relevant,
        should_ignore=should_ignore,
        confidence=confidence,
        reason=reason,
    )


def route_utterance(
    text: str,
) -> UtteranceRoute:
    if is_non_linguistic_noise(text):
        return UtteranceRoute(
            route_type="noise",
            is_relevant=False,
            should_ignore=True,
            confidence=1.0,
            reason="The input does not contain meaningful linguistic content.",
        )

    prompt = build_utterance_route_prompt(text)
    raw_response = generate_llm_response(prompt)

    try:
        payload = parse_utterance_route_json(raw_response)
    except json.JSONDecodeError:
        return build_fallback_route(
            reason=(
                "The LLM did not return valid JSON, so the utterance was "
                "treated as a response request."
            ),
        )

    return normalise_route_payload(payload)