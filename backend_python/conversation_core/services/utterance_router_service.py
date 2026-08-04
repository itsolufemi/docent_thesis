import json
import re
from time import perf_counter

import httpx

from config import settings
from conversation_core.schemas.classifier_domain_schemas import (
    ClassifierDomainProfile,
)
from conversation_core.schemas.utterance_route_schemas import UtteranceRoute


VALID_ROUTE_TYPES = {
    "noise",
    "response_request",
    "call_to_action",
    "interruption",
}
VALID_FLOOR_INTENTS = {
    "none",
    "backchannel",
    "hold_floor",
    "take_floor",
}
CLASSIFIER_REQUEST_TIMEOUT_SECONDS = 20.0
CLASSIFIER_REQUEST_OPTIONS = {
    "temperature": 0,
    "num_predict": 160,
}
CLASSIFIER_REQUIRED_FIELDS = {
    "route_type",
    "floor_intent",
    "requires_retrieval",
    "proposed_action",
    "candidate_subjects",
}


def build_utterance_route_response_format(
    domain_profile: ClassifierDomainProfile,
) -> dict:
    valid_actions = sorted(
        get_valid_action_names(domain_profile)
    )
    proposed_action_options = [
        {
            "type": "null",
        },
    ]

    if valid_actions:
        proposed_action_options.insert(
            0,
            {
                "type": "string",
                "enum": valid_actions,
            },
        )

    return {
        "type": "object",
        "properties": {
            "route_type": {
                "type": "string",
                "enum": sorted(VALID_ROUTE_TYPES),
            },
            "floor_intent": {
                "type": "string",
                "enum": sorted(VALID_FLOOR_INTENTS),
            },
            "requires_retrieval": {
                "type": "boolean",
            },
            "proposed_action": {
                "anyOf": (
                    proposed_action_options
                ),
            },
            "candidate_subjects": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": sorted(
            CLASSIFIER_REQUIRED_FIELDS
        ),
        "additionalProperties": False,
    }


def validate_utterance_route_payload(
    payload: dict,
) -> None:
    missing_fields = (
        CLASSIFIER_REQUIRED_FIELDS
        - payload.keys()
    )

    if missing_fields:
        raise ValueError(
            "Classifier response is missing fields: "
            + ", ".join(sorted(missing_fields))
        )

    if payload["route_type"] not in (
        VALID_ROUTE_TYPES
    ):
        raise ValueError(
            "Classifier returned an invalid route "
            "type."
        )

    if payload["floor_intent"] not in (
        VALID_FLOOR_INTENTS
    ):
        raise ValueError(
            "Classifier returned an invalid floor "
            "intent."
        )

    if not isinstance(
        payload["requires_retrieval"],
        bool,
    ):
        raise ValueError(
            "Classifier retrieval decision must be "
            "boolean."
        )

    if (
        payload["proposed_action"] is not None
        and not isinstance(
            payload["proposed_action"],
            str,
        )
    ):
        raise ValueError(
            "Classifier action must be a string or "
            "null."
        )

    if (
        not isinstance(
            payload["candidate_subjects"],
            list,
        )
        or not all(
            isinstance(subject, str)
            for subject
            in payload["candidate_subjects"]
        )
    ):
        raise ValueError(
            "Classifier subjects must be a list of "
            "strings."
        )


def request_streaming_utterance_route(
    *,
    prompt: str,
    domain_profile: ClassifierDomainProfile,
    model: str | None = None,
    timeout: float = (
        CLASSIFIER_REQUEST_TIMEOUT_SECONDS
    ),
) -> UtteranceRoute:
    started_at = perf_counter()
    request_payload = {
        "model": (
            model
            or settings.ollama_classifier_model
        ),
        "prompt": prompt,
        "stream": True,
        "think": False,
        "format": (
            build_utterance_route_response_format(
                domain_profile
            )
        ),
        "options": CLASSIFIER_REQUEST_OPTIONS,
    }
    accumulated_response = ""

    with httpx.stream(
        "POST",
        f"{settings.ollama_base_url}/api/generate",
        json=request_payload,
        timeout=timeout,
    ) as response:
        response.raise_for_status()

        for line in response.iter_lines():
            if (
                perf_counter() - started_at
                >= timeout
            ):
                response.close()
                raise TimeoutError(
                    "Classifier stream exceeded its "
                    "absolute request deadline."
                )

            if not line:
                continue

            chunk = json.loads(line)
            accumulated_response += (
                chunk.get("response", "")
            )

            if accumulated_response:
                try:
                    payload = (
                        parse_utterance_route_json(
                            accumulated_response
                        )
                    )
                    validate_utterance_route_payload(
                        payload
                    )
                except (
                    json.JSONDecodeError,
                    ValueError,
                ):
                    pass
                else:
                    route = normalise_route_payload(
                        payload=payload,
                        domain_profile=domain_profile,
                    )
                    response.close()
                    return route

            if chunk.get("done"):
                break

    raise ValueError(
        "Classifier stream ended without a valid "
        "structured response."
    )


def add_routing_time(
    route: UtteranceRoute,
    started_at: float,
) -> UtteranceRoute:
    route.routing_seconds = round(
        perf_counter() - started_at,
        4,
    )
    return route

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


def format_retrieval_policy(
    domain_profile: ClassifierDomainProfile,
) -> str:
    policy = domain_profile.retrieval_policy

    if policy is None:
        return (
            "No retrieval capability is available for the active "
            "domain. Set requires_retrieval to false."
        )

    retrieve_for = "\n".join(
        f"- {item}"
        for item in policy.retrieve_for
    )
    do_not_retrieve_for = "\n".join(
        f"- {item}"
        for item in policy.do_not_retrieve_for
    )

    return f"""
Retrieval capability:
{policy.description}

Set requires_retrieval to true for:
{retrieve_for or "- No cases specified."}

Set requires_retrieval to false for:
{do_not_retrieve_for or "- No cases specified."}
""".strip()


def format_available_actions(
    domain_profile: ClassifierDomainProfile,
) -> str:
    if not domain_profile.available_actions:
        return (
            "No user-facing actions are available for the active "
            "domain. Do not use call_to_action."
        )

    formatted_actions: list[str] = []

    for action in domain_profile.available_actions:
        examples = "\n".join(
            f"- {example}"
            for example in action.example_requests
        )

        formatted_actions.append(
            f"""
Action name: {action.name}
Description: {action.description}
Example requests:
{examples or "- No examples supplied."}
""".strip()
        )

    return "\n\n".join(formatted_actions)


def build_utterance_route_prompt(
    text: str,
    domain_profile: ClassifierDomainProfile,
    *,
    assistant_was_speaking: bool = False,
    compact_response: bool = False,
) -> str:
    retrieval_policy = format_retrieval_policy(domain_profile)
    available_actions = format_available_actions(domain_profile)

    if compact_response:
        response_shape = """
{
  "route_type": "noise | response_request | call_to_action | interruption",
  "floor_intent": "none | backchannel | hold_floor | take_floor",
  "requires_retrieval": false,
  "proposed_action": null,
  "candidate_subjects": []
}
""".strip()
    else:
        response_shape = """
{
  "route_type": "noise | response_request | call_to_action | interruption",
  "floor_intent": "none | backchannel | hold_floor | take_floor",
  "requires_retrieval": false,
  "proposed_action": null,
  "candidate_subjects": [],
  "is_relevant": true,
  "should_ignore": false,
  "confidence": 0.0,
  "reason": "brief explanation"
}
""".strip()

    return f"""
You are a fast utterance classifier for a general voice-led
conversational AI engine.

Your task is classification only. Do not answer the user.

ACTIVE DOMAIN

Name:
{domain_profile.domain_name}

Description:
{domain_profile.domain_description}

ROUTE TYPES

1. noise

Use when the input is not meaningful conversational language.
Examples include empty input, meaningless symbols, accidental
transcription and random non-word fragments.

2. response_request

Use for a meaningful conversational turn that expects a verbal
response. This includes questions, greetings, acknowledgements,
requests for explanation, follow-up turns and ordinary movement
between subjects in an existing conversation.

Moving to the next subject within an ongoing conversation or tour is
normally a response_request. It is not automatically a call_to_action.

Such next, previous or current-subject navigation should use existing
conversation state and should not require retrieval unless the user
also asks for new factual or interpretive information.

3. call_to_action

Use only when the user explicitly requests one of the user-facing
actions supplied by the active domain.

Do not invent actions.

4. interruption

Use when the user is stopping, pausing, correcting, redirecting or
cutting into the assistant's current speaking or acting turn.

RETRIEVAL POLICY

{retrieval_policy}

AVAILABLE USER-FACING ACTIONS

{available_actions}

ASSISTANT FLOOR STATE

The assistant was speaking when this user contribution began:
{assistant_was_speaking}

FLOOR INTENT

none:
No meaningful floor-management behaviour is present.

backchannel:
A brief acknowledgement that supports the assistant continuing,
such as "mm-hm", "right", "okay" or "I see", when it does not
introduce a new question, correction or request.

hold_floor:
The user appears to be continuing an incomplete contribution and
has not yet produced a complete request.

take_floor:
The user asks a question, corrects, redirects, stops or otherwise
produces a meaningful contribution that should receive the floor.

CLASSIFICATION RULES

- proposed_action must be one of the supplied action names or null.
- If no supplied action matches, do not use call_to_action.
- candidate_subjects should contain only subjects explicitly named
  or clearly expressed in this utterance.
- Candidate subjects are provisional extractions. They do not update
  conversation state.
- requires_retrieval means that the active domain's retrieval system
  should be attempted. It does not guarantee that evidence will be
  found.
- Default meaningful but uncertain input to response_request.

USER UTTERANCE

{text}

Return only one JSON object using this exact shape:

{response_shape}
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
        floor_intent="none",
        requires_retrieval=False,
        proposed_action=None,
        candidate_subjects=[],
        is_relevant=True,
        should_ignore=False,
        confidence=0.4,
        reason=reason,
    )


def get_valid_action_names(
    domain_profile: ClassifierDomainProfile,
) -> set[str]:
    return {
        action.name
        for action in domain_profile.available_actions
    }


def normalise_boolean(
    value,
    default: bool = False,
) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalised = value.strip().lower()

        if normalised == "true":
            return True

        if normalised == "false":
            return False

    return default


def normalise_route_payload(
    payload: dict,
    domain_profile: ClassifierDomainProfile,
) -> UtteranceRoute:
    route_type = payload.get("route_type")

    if route_type not in VALID_ROUTE_TYPES:
        return build_fallback_route(
            reason="The LLM returned an invalid route type, so the utterance was treated as a response request.",
        )

    valid_action_names = get_valid_action_names(domain_profile)
    proposed_action = payload.get("proposed_action")

    if proposed_action not in valid_action_names:
        proposed_action = None

    if route_type != "call_to_action":
        proposed_action = None

    if route_type == "call_to_action" and proposed_action is None:
        route_type = "response_request"

    floor_intent = payload.get(
        "floor_intent",
        "none",
    )

    if floor_intent not in VALID_FLOOR_INTENTS:
        floor_intent = "none"

    requires_retrieval = normalise_boolean(
        payload.get("requires_retrieval")
    )

    raw_candidate_subjects = payload.get("candidate_subjects", [])

    if not isinstance(raw_candidate_subjects, list):
        raw_candidate_subjects = []

    candidate_subjects = [
        str(subject).strip()
        for subject in raw_candidate_subjects
        if str(subject).strip()
    ]

    is_relevant = bool(payload.get("is_relevant", route_type != "noise"))
    should_ignore = bool(payload.get("should_ignore", route_type == "noise"))

    if route_type == "noise":
        floor_intent = "none"
        is_relevant = False
        should_ignore = True
        requires_retrieval = False
        proposed_action = None
        candidate_subjects = []

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
        floor_intent=floor_intent,
        requires_retrieval=requires_retrieval,
        proposed_action=proposed_action,
        candidate_subjects=candidate_subjects,
        is_relevant=is_relevant,
        should_ignore=should_ignore,
        confidence=confidence,
        reason=reason,
    )


def route_utterance(
    text: str,
    domain_profile: ClassifierDomainProfile,
    *,
    assistant_was_speaking: bool = False,
) -> UtteranceRoute:
    started_at = perf_counter()

    if is_non_linguistic_noise(text):
        return add_routing_time(
            UtteranceRoute(
                route_type="noise",
                floor_intent="none",
                requires_retrieval=False,
                proposed_action=None,
                candidate_subjects=[],
                is_relevant=False,
                should_ignore=True,
                confidence=1.0,
                reason=(
                    "The input does not contain meaningful linguistic "
                    "content."
                ),
            ),
            started_at,
        )

    if not settings.ollama_classifier_model:
        raise ValueError(
            "OLLAMA_CLASSIFIER_MODEL must be configured before "
            "classifying utterances."
        )

    prompt = build_utterance_route_prompt(
        text=text,
        domain_profile=domain_profile,
        assistant_was_speaking=assistant_was_speaking,
        compact_response=True,
    )
    try:
        route = request_streaming_utterance_route(
            prompt=prompt,
            domain_profile=domain_profile,
        )
    except (
        httpx.HTTPError,
        json.JSONDecodeError,
        TimeoutError,
        ValueError,
    ):
        route = build_fallback_route(
            reason=(
                "The LLM did not return a valid "
                "structured result, so the utterance "
                "was treated as a response request."
            ),
        )

    return add_routing_time(
        route,
        started_at,
    )
