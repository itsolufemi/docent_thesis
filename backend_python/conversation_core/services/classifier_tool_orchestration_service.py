import logging
from time import perf_counter

from conversation_core.memory.conversation_store import (
    get_active_branch,
    get_recent_conversation_history,
)
from conversation_core.schemas.classifier_tool_schemas import (
    ClassifierToolAudit,
    ClassifierToolRoundResult,
)
from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)
from conversation_core.schemas.tool_schemas import (
    ToolExecutionContext,
)
from conversation_core.services.llm_service import (
    build_ollama_tool_definitions,
    collect_streamed_ollama_chat_response,
    parse_ollama_tool_calls,
)
from conversation_core.services.prompt_service import (
    format_conversation_branch_for_prompt,
)
from conversation_core.tools.core_tool_registry import (
    core_tool_registry,
)
from conversation_core.tools.utterance_classifier_tool import (
    CLASSIFY_UTTERANCE_TOOL_NAME,
)
from conversation_core.services.utterance_router_service import (
    format_available_actions,
    format_retrieval_policy,
)
from docent.config.docent_classifier_profile import (
    docent_classifier_profile,
)


logger = logging.getLogger(__name__)


class ClassifierToolProtocolError(
    RuntimeError
):
    def __init__(
        self,
        message: str,
        *,
        audit: ClassifierToolAudit,
    ) -> None:
        super().__init__(message)
        self.audit = audit


def build_required_classifier_tool_prompt(
    *,
    text: str,
    conversation_id: str,
    assistant_was_speaking: bool = False,
) -> str:
    dialogue_history = (
        get_recent_conversation_history(
            conversation_id=conversation_id,
            limit=4,
        )
    )
    active_branch = get_active_branch(
        conversation_id=conversation_id,
    )
    dialogue_context = "\n".join(
        f"{turn.role}: {turn.content}"
        for turn in dialogue_history
    )
    branch_context = (
        format_conversation_branch_for_prompt(
            active_branch
        )
    )
    retrieval_policy = (
        format_retrieval_policy(
            docent_classifier_profile
        )
    )
    available_actions = (
        format_available_actions(
            docent_classifier_profile
        )
    )

    return f"""
Before answering the user, classify the latest
utterance and call classify_utterance exactly once.

Pass the user's complete latest utterance
unchanged and put your classification in the
remaining tool arguments.

Do not answer the user, retrieve information,
or call another tool until the classification
result has been returned.

ROUTE RULES

- noise: no meaningful conversational language.
- response_request: a meaningful turn expecting a
  verbal response, including greetings, questions,
  explanations, follow-ups, and ordinary movement
  between subjects.
- call_to_action: only an explicit request for one
  of the available actions below.
- interruption: the user stops, corrects, redirects,
  or cuts into the assistant while it is speaking.

FLOOR RULES

- none: no meaningful floor behaviour.
- backchannel: a brief acknowledgement supporting
  the assistant continuing.
- hold_floor: the user is continuing an incomplete
  contribution.
- take_floor: a question, correction, redirection,
  stop, or meaningful contribution needing a turn.

RETRIEVAL POLICY

{retrieval_policy}

AVAILABLE ACTIONS

{available_actions}

The assistant was speaking when this contribution
began:
{assistant_was_speaking}

candidate_subjects must contain only subjects named
or clearly expressed in the latest utterance.
Use proposed_action "none" when no available action
was explicitly requested.

RECENT DIALOGUE

{dialogue_context or "No previous dialogue."}

ACTIVE CONVERSATION BRANCH

{branch_context}

LATEST USER UTTERANCE

{text}
""".strip()


def _build_audit(
    *,
    classifier_call_count: int,
    invalid_classifier_arguments: bool,
    model_returned_content: bool,
    model_to_tool_call_seconds: float,
    classifier_execution_seconds: float,
    total_seconds: float,
) -> ClassifierToolAudit:
    return ClassifierToolAudit(
        classifier_call_count=(
            classifier_call_count
        ),
        classifier_called_exactly_once=(
            classifier_call_count == 1
        ),
        classifier_omitted=(
            classifier_call_count == 0
        ),
        classifier_called_more_than_once=(
            classifier_call_count > 1
        ),
        invalid_classifier_arguments=(
            invalid_classifier_arguments
        ),
        model_returned_content=(
            model_returned_content
        ),
        model_to_tool_call_seconds=round(
            model_to_tool_call_seconds,
            4,
        ),
        classifier_execution_seconds=round(
            classifier_execution_seconds,
            4,
        ),
        total_seconds=round(
            total_seconds,
            4,
        ),
    )


def run_required_classifier_tool_round(
    *,
    text: str,
    conversation_id: str,
    assistant_was_speaking: bool = False,
    main_model: str | None = None,
    main_model_think: bool | None = None,
) -> ClassifierToolRoundResult:
    cleaned_text = text.strip()

    if not cleaned_text:
        raise ValueError(
            "The latest utterance cannot be empty."
        )

    round_started_at = perf_counter()
    prompt = build_required_classifier_tool_prompt(
        text=cleaned_text,
        conversation_id=conversation_id,
        assistant_was_speaking=(
            assistant_was_speaking
        ),
    )
    tools = build_ollama_tool_definitions(
        tool_names={
            CLASSIFY_UTTERANCE_TOOL_NAME
        },
        include_classifier=True,
    )
    response_data = (
        collect_streamed_ollama_chat_response(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        tools=tools,
        model=main_model,
        think=main_model_think,
        )
    )
    model_to_tool_call_seconds = (
        perf_counter() - round_started_at
    )
    response_message = (
        response_data.get("message") or {}
    )
    model_returned_content = bool(
        str(
            response_message.get(
                "content",
                "",
            )
        ).strip()
    )
    tool_calls = parse_ollama_tool_calls(
        response_message
    )
    classifier_calls = [
        tool_call
        for tool_call in tool_calls
        if (
            tool_call.name
            == CLASSIFY_UTTERANCE_TOOL_NAME
        )
    ]
    classifier_call_count = len(
        classifier_calls
    )
    invalid_arguments = False

    if (
        len(tool_calls) != 1
        or classifier_call_count != 1
    ):
        audit = _build_audit(
            classifier_call_count=(
                classifier_call_count
            ),
            invalid_classifier_arguments=False,
            model_returned_content=(
                model_returned_content
            ),
            model_to_tool_call_seconds=(
                model_to_tool_call_seconds
            ),
            classifier_execution_seconds=0.0,
            total_seconds=(
                perf_counter()
                - round_started_at
            ),
        )
        logger.warning(
            "Mandatory classifier tool call "
            "protocol failed: %s",
            audit.model_dump_json(),
        )
        raise ClassifierToolProtocolError(
            (
                "The mandatory first round must "
                "contain exactly one "
                "classify_utterance tool call."
            ),
            audit=audit,
        )

    tool_call = classifier_calls[0]
    supplied_utterance = (
        tool_call.arguments.get("utterance")
    )

    if (
        not isinstance(
            supplied_utterance,
            str,
        )
        or supplied_utterance != cleaned_text
    ):
        invalid_arguments = True
        audit = _build_audit(
            classifier_call_count=1,
            invalid_classifier_arguments=True,
            model_returned_content=(
                model_returned_content
            ),
            model_to_tool_call_seconds=(
                model_to_tool_call_seconds
            ),
            classifier_execution_seconds=0.0,
            total_seconds=(
                perf_counter()
                - round_started_at
            ),
        )
        logger.warning(
            "Mandatory classifier tool arguments "
            "were invalid: %s",
            audit.model_dump_json(),
        )
        raise ClassifierToolProtocolError(
            (
                "classify_utterance must receive the "
                "latest utterance unchanged."
            ),
            audit=audit,
        )

    classifier_started_at = perf_counter()
    execution_result = (
        core_tool_registry.execute(
            tool_call=tool_call,
            context=ToolExecutionContext(
                conversation_id=conversation_id,
                assistant_was_speaking=(
                    assistant_was_speaking
                ),
            ),
        )
    )
    classifier_execution_seconds = (
        perf_counter() - classifier_started_at
    )

    if not execution_result.success:
        invalid_arguments = bool(
            execution_result.data.get(
                "validation_errors"
            )
        )
        audit = _build_audit(
            classifier_call_count=1,
            invalid_classifier_arguments=(
                invalid_arguments
            ),
            model_returned_content=(
                model_returned_content
            ),
            model_to_tool_call_seconds=(
                model_to_tool_call_seconds
            ),
            classifier_execution_seconds=(
                classifier_execution_seconds
            ),
            total_seconds=(
                perf_counter()
                - round_started_at
            ),
        )
        logger.warning(
            "Mandatory classifier tool execution "
            "failed: %s; details=%s",
            audit.model_dump_json(),
            execution_result.data,
        )
        raise ClassifierToolProtocolError(
            execution_result.message,
            audit=audit,
        )

    utterance_route = (
        UtteranceRoute.model_validate(
            execution_result.data.get(
                "utterance_route"
            )
        )
    )
    audit = _build_audit(
        classifier_call_count=1,
        invalid_classifier_arguments=False,
        model_returned_content=(
            model_returned_content
        ),
        model_to_tool_call_seconds=(
            model_to_tool_call_seconds
        ),
        classifier_execution_seconds=(
            classifier_execution_seconds
        ),
        total_seconds=(
            perf_counter() - round_started_at
        ),
    )
    logger.info(
        "Mandatory classifier tool round "
        "completed: %s",
        audit.model_dump_json(),
    )

    return ClassifierToolRoundResult(
        utterance=cleaned_text,
        utterance_route=utterance_route,
        audit=audit,
        prompt=prompt,
        continuation_messages=[
            {
                "role": "user",
                "content": prompt,
            },
            response_message,
            {
                "role": "tool",
                "tool_name": (
                    CLASSIFY_UTTERANCE_TOOL_NAME
                ),
                "content": (
                    execution_result
                    .model_dump_json()
                ),
            },
        ],
    )


def build_classifier_tool_resume_messages(
    *,
    classifier_round: (
        ClassifierToolRoundResult
    ),
    response_prompt: str,
) -> list[dict]:
    return [
        *classifier_round.continuation_messages,
        {
            "role": "user",
            "content": (
                "The mandatory classification "
                "round is complete. Use the "
                "resolved context below and now "
                "answer the user's latest "
                "utterance.\n\n"
                f"{response_prompt}"
            ),
        },
    ]
