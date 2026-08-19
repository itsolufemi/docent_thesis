from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)
from conversation_core.services.utterance_router_service import (
    route_utterance,
)
from docent.config.docent_classifier_profile import (
    docent_classifier_profile,
)


def classify_docent_utterance(
    text: str,
    assistant_was_speaking: bool,
) -> UtteranceRoute:
    return route_utterance(
        text=text,
        domain_profile=docent_classifier_profile,
        assistant_was_speaking=assistant_was_speaking,
    )
