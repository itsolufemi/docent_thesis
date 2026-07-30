from collections.abc import Callable

from conversation_core.schemas.query_schemas import QueryResponse
from conversation_core.schemas.turn_buffer_schemas import (
    TurnBufferEvent,
    TurnProcessingResult,
)
from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)
from conversation_core.schemas.classifier_tool_schemas import (
    ClassifierToolRoundResult,
)
from conversation_core.services.query_service import QueryEngine
from conversation_core.services.turn_buffer_service import process_turn_event

UtteranceClassifier = Callable[
    [str, bool],
    UtteranceRoute,
]
ClassifierToolRunner = Callable[
    ...,
    ClassifierToolRoundResult,
]


def process_conversation_turn(
    event: TurnBufferEvent,
    query_engine: QueryEngine,
    *,
    utterance_classifier: UtteranceClassifier | None = None,
    classifier_tool_runner: (
        ClassifierToolRunner | None
    ) = None,
    include_debug: bool = False,
) -> TurnProcessingResult:
    turn_result = process_turn_event(event)

    if not turn_result.should_finalise_turn:
        return TurnProcessingResult(
            turn=turn_result,
            utterance_route=None,
            query=None,
        )

    finalised_utterance = turn_result.finalised_utterance

    if not finalised_utterance:
        return TurnProcessingResult(
            turn=turn_result,
            utterance_route=None,
            query=None,
        )

    utterance_route = None
    classifier_tool_result = None

    if classifier_tool_runner is not None:
        classifier_tool_result = (
            classifier_tool_runner(
                text=finalised_utterance,
                conversation_id=(
                    event.conversation_id
                ),
                assistant_was_speaking=(
                    event.assistant_was_speaking
                ),
            )
        )
        utterance_route = (
            classifier_tool_result
            .utterance_route
        )

        query_result = (
            query_engine
            .generate_classifier_tool_streaming_response(
                text=finalised_utterance,
                classifier_round=(
                    classifier_tool_result
                ),
                conversation_id=(
                    event.conversation_id
                ),
                subject_reference=None,
                include_debug=include_debug,
            )
        )
        query_response = QueryResponse(
            request=query_result.request,
            response=query_result.response,
            conversation_id=(
                query_result.conversation_id
            ),
            subject_reference=(
                query_result.subject_reference
            ),
            sources=query_result.sources,
            debug=query_result.debug,
        )

        return TurnProcessingResult(
            turn=turn_result,
            utterance_route=utterance_route,
            classifier_tool=(
                classifier_tool_result
            ),
            query=query_response,
        )

    if utterance_classifier is not None:
        utterance_route = utterance_classifier(
            finalised_utterance,
            event.assistant_was_speaking,
        )

    query_result = query_engine.generate_response(
        text=finalised_utterance,
        conversation_id=event.conversation_id,
        subject_reference=None,
        utterance_route=utterance_route,
        include_debug=include_debug,
    )

    query_response = QueryResponse(
        request=query_result.request,
        response=query_result.response,
        conversation_id=query_result.conversation_id,
        subject_reference=query_result.subject_reference,
        sources=query_result.sources,
        debug=query_result.debug,
    )

    return TurnProcessingResult(
        turn=turn_result,
        utterance_route=utterance_route,
        classifier_tool=None,
        query=query_response,
    )
