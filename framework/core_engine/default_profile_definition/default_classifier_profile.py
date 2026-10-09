from core_engine.schemas.classifier_domain_schemas import (
    ClassifierDomainProfile,
)


default_classifier_profile = ClassifierDomainProfile(
    domain_name="General conversation",
    domain_description=(
        "A domain-neutral conversational assistant used to exercise "
        "framework conversation features without application-specific "
        "knowledge, retrieval policies, or actions."
    ),
)
