from fastapi import APIRouter

from conversation_core.schemas.trp_schemas import (
    TRPPrediction,
    TRPPredictionRequest,
)
from conversation_core.services.trp_service import (
    predict_transition_relevance,
)


router = APIRouter()


@router.post(
    "/api/conversation/trp",
    response_model=TRPPrediction,
)
def read_trp_prediction(
    request: TRPPredictionRequest,
):
    return predict_transition_relevance(
        partial_utterance=request.partial_utterance,
        previous_turns=request.previous_turns,
    )
