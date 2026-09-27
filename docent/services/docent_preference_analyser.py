from __future__ import annotations

import json

from time import perf_counter

from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.services.llm_service import generate_llm_response
from conversation_core.services.prompt_service import (
    format_dialogue_history_for_prompt,
)
from docent.schemas.preference_schemas import (
    DocentPreferenceEvidence,
    DocentPreferenceState,
)


DOCENT_PREFERENCE_ANALYSIS_INSTRUCTIONS = """
You analyse a museum visitor's conversational preferences. Do not answer the
visitor. Return exactly one JSON object describing only evidence present in
the current visitor utterance and its recent conversational context.

Interest categories:
- interpretation: meaning, symbolism, themes, or interpretation;
- technique: materials, making, composition, colour, brushwork, or process;
- historical_social_context: political, social, cultural, or period context;
- narrative: depicted people, events, action, or story;
- artist_context: the artist, their life, career, influences, or typical work.

For each evidenced interest, add an object to interest_signals with category
and strength: weak, medium, or strong. Use an empty list when there is no
meaningful evidence. Do not infer technical expertise merely from interest in
technique.

Contextual acknowledgements such as "Yes, tell me more" may provide interest
evidence when the preceding dialogue offered a specific facet. Ordinary
backchannels provide no evidence. Existing preference weights are context,
not evidence: do not repeat them as signals without support from this turn.

Return this exact shape and no markdown:
{
  "interest_signals": [
    {"category": "technique", "strength": "strong"}
  ]
}
""".strip()


def _extract_json_object(text: str) -> str:
    stripped = text.strip()

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError(
            "Preference analyser did not return a JSON object."
        )

    return stripped[start:end + 1]


def build_docent_preference_analysis_prompt(
    *,
    dialogue_history: list[DialogueTurn],
    user_input: str,
    preference_state: DocentPreferenceState,
) -> str:
    formatted_history = format_dialogue_history_for_prompt(
        dialogue_history=dialogue_history,
        user_label="Visitor",
        assistant_label="Docent",
    )

    return f"""
{DOCENT_PREFERENCE_ANALYSIS_INSTRUCTIONS}

CURRENT PREFERENCE MODEL
{preference_state.model_dump_json(indent=2)}

RECENT DIALOGUE BEFORE THIS TURN
{formatted_history}

CURRENT VISITOR UTTERANCE
{user_input}

JSON:
""".strip()


def analyse_docent_preferences(
    dialogue_history: list[DialogueTurn],
    user_input: str,
    preference_state: DocentPreferenceState,
) -> tuple[DocentPreferenceEvidence, dict]:
    started_at = perf_counter()
    prompt = build_docent_preference_analysis_prompt(
        dialogue_history=dialogue_history,
        user_input=user_input,
        preference_state=preference_state,
    )
    raw_response = generate_llm_response(
        prompt=prompt,
        options={"temperature": 0},
        think=False,
    )
    validation_error: str | None = None

    try:
        evidence = DocentPreferenceEvidence.model_validate(
            json.loads(_extract_json_object(raw_response))
        )
    except Exception as error:
        validation_error = str(error)
        evidence = DocentPreferenceEvidence()

    return evidence, {
        "analysis_seconds": round(
            perf_counter() - started_at,
            4,
        ),
        "raw_response": raw_response,
        "validation_error": validation_error,
    }
