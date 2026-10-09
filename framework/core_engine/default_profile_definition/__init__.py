"""Domain-neutral prompt roles and conversational rules."""

from core_engine.default_profile_definition.default_profile_definition import (
    CORE_BEHAVIOURAL_RULES,
    CORE_CONVERSATIONAL_RULES,
    DEFAULT_ASSISTANT_ROLE,
    DIRECT_ROUTING_RULES,
)
from core_engine.default_profile_definition.default_classifier_profile import (
    default_classifier_profile,
)

__all__ = [
    "CORE_BEHAVIOURAL_RULES",
    "CORE_CONVERSATIONAL_RULES",
    "DEFAULT_ASSISTANT_ROLE",
    "DIRECT_ROUTING_RULES",
    "default_classifier_profile",
]
