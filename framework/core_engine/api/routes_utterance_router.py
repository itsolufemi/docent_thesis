from fastapi import APIRouter
from pydantic import BaseModel

from core_engine.schemas.classifier_domain_schemas import (
    ClassifierDomainProfile,
)
from core_engine.schemas.utterance_route_schemas import UtteranceRoute
from core_engine.services.utterance_router_service import route_utterance


class UtteranceRouteRequest(BaseModel):
    text: str
    assistant_was_speaking: bool = False


def create_utterance_router(
    domain_profile: ClassifierDomainProfile,
) -> APIRouter:
    """Create the route with an application-supplied domain profile."""
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
            domain_profile=domain_profile,
            assistant_was_speaking=(
                request.assistant_was_speaking
            ),
        )

    return router
