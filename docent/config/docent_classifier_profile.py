from conversation_core.schemas.classifier_domain_schemas import (
    ClassifierActionDefinition,
    ClassifierDomainProfile,
    RetrievalClassificationPolicy,
)


docent_classifier_profile = ClassifierDomainProfile(
    domain_name="Docent",
    domain_description=(
        "A voice-led conversational guide for artworks, artists, "
        "galleries, museum collections and guided cultural-space "
        "conversations."
    ),
    retrieval_policy=RetrievalClassificationPolicy(
        description=(
            "Docent can search curated information concerning "
            "artworks, artists, artistic periods, styles, rooms, "
            "collections and related cultural subjects."
        ),
        retrieve_for=[
            (
                "Requests for factual, descriptive or interpretive "
                "information about art."
            ),
            (
                "Questions about explicitly named or contextually "
                "implied artworks and artists."
            ),
            (
                "Comparisons involving artworks, artists, styles "
                "or periods."
            ),
            (
                "Requests to construct a tour or another ordered "
                "sequence of artworks."
            ),
        ],
        do_not_retrieve_for=[
            "Greetings and introductions.",
            "Questions about the assistant itself.",
            "Ordinary acknowledgements and social conversation.",
            (
                "Requests that can be answered solely from the "
                "existing conversation state."
            ),
            (
                "Requests to move to the next, previous or current "
                "subject in an ongoing tour."
            ),
        ],
    ),
    available_actions=[
        ClassifierActionDefinition(
            name="start_highlights_tour",
            description=(
                "Begin a guided highlights tour or another supported "
                "tour experience."
            ),
            example_requests=[
                "Give me a highlights tour.",
                "Start a tour of portraits.",
                "Take me through three paintings in this room.",
            ],
        ),
        ClassifierActionDefinition(
            name="stop_tour",
            description=(
                "End or abandon the visitor's current tour."
            ),
            example_requests=[
                "Stop the tour.",
                "I don't want to continue.",
                "Let's end this and talk about something else.",
            ],
        ),
    ],
)
