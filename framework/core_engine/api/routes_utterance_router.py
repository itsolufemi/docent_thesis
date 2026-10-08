from fastapi import APIRouter
from pydantic import BaseModel

from core_engine.schemas.utterance_route_schemas import UtteranceRoute
from core_engine.services.utterance_router_service import route_utterance
from apps.docent.config.docent_classifier_profile import docent_classifier_profile


class UtteranceRouteRequest(BaseModel):
    text: str
    assistant_was_speaking: bool = False


router = APIRouter()


@router.post(
    "/api/conversation/utterance-route",
    response_model=UtteranceRoute,
)
def read_utterance_route(
    request: UtteranceRouteRequest,
):
    return route_utterance(
        text=request.text,
        domain_profile=docent_classifier_profile,
        assistant_was_speaking=(
            request.assistant_was_speaking
        ),
    )
