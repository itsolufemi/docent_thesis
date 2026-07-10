from typing import Literal

from pydantic import BaseModel


UtteranceRouteType = Literal[
    "noise",
    "response_request",
    "call_to_action",
    "interruption",
]


class UtteranceRoute(BaseModel):
    route_type: UtteranceRouteType
    is_relevant: bool
    should_ignore: bool
    confidence: float
    reason: str