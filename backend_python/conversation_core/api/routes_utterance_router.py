from fastapi import APIRouter
from pydantic import BaseModel

from conversation_core.schemas.utterance_route_schemas import UtteranceRoute
from conversation_core.services.utterance_router_service import route_utterance


class UtteranceRouteRequest(BaseModel):
    text: str


router = APIRouter()


@router.post(
    "/api/conversation/utterance-route",
    response_model=UtteranceRoute,
)
def read_utterance_route(
    request: UtteranceRouteRequest,
):
    return route_utterance(request.text)