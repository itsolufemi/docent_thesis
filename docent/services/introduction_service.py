from conversation_core.schemas.introduction_schemas import (
    IntroductionDefinition,
)


def build_docent_introduction() -> IntroductionDefinition:
    return IntroductionDefinition(
        prompt=(
            "Introduce yourself briefly to the visitor as Docent, "
            "a conversational gallery guide. Welcome them naturally "
            "and ask how they are doing today. Keep the introduction "
            "to one or two short sentences."
        ),
        fallback_text=(
            "Hello, I'm Docent, let's talk about art! "
            "How are you doing today?"
        ),
        store_as_dialogue_turn=True,
    )
