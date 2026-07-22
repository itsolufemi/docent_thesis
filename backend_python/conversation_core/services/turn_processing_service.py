from conversation_core.schemas.query_schemas import QueryResponse
from conversation_core.schemas.turn_buffer_schemas import (
    TurnBufferEvent,
    TurnProcessingResult,
)
from conversation_core.services.query_service import QueryEngine
from conversation_core.services.turn_buffer_service import process_turn_event


def process_conversation_turn(
    event: TurnBufferEvent,
    query_engine: QueryEngine,
    *,
    include_debug: bool = False,
) -> TurnProcessingResult:
    turn_result = process_turn_event(event)

    if not turn_result.should_finalise_turn:
        return TurnProcessingResult(
            turn=turn_result,
            query=None,
        )

    finalised_utterance = turn_result.finalised_utterance

    if not finalised_utterance:
        return TurnProcessingResult(
            turn=turn_result,
            query=None,
        )

    query_result = query_engine.generate_response(
        text=finalised_utterance,
        conversation_id=event.conversation_id,
        subject_reference=None,
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
        query=query_response,
    )
