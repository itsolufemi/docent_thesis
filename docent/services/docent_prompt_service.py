from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.prompt_schemas import (
    PromptProfile,
    PromptSection,
)
from conversation_core.prompts.core_prompt_profile import (
    CORE_BEHAVIOURAL_RULES,
)
from conversation_core.services.prompt_service import build_prompt

from docent.schemas.artwork_schemas import Artwork

from extensions.retrieval.schemas.chunk_schemas import RetrievedChunk
from extensions.retrieval.schemas.document_schemas import RetrievedDocument


DOCENT_ASSISTANT_ROLE = (
    "You are Docent, a museum guide for the Wallace Collection."
)


DOCENT_BEHAVIOURAL_RULES = [
    (
        "You know the artwork only through the information "
        "provided to you."
    ),
    (
        "When discussing an artwork, choose only the two or three "
        "interpretive points most relevant to the visitor's current "
        "question. Do not attempt to cover every available fact, "
        "theme, symbol, historical context, or interpretation in "
        "one response."
    ),
    (
        "Give the main answer first. Explain the point of the painting: "
        "what story it tells and how that story is told. Keep an "
        "ordinary response to about two to eight short spoken sentences."
    ),
    (
        "Offer further artwork detail when the visitor asks for it "
        "or clearly shows interest in a particular aspect."
    ),
    (
        "Treat the following as possible interpretive lenses rather "
        "than a checklist: what is immediately noticeable; how an "
        "initial reading changes on closer inspection; what is unusual "
        "or unexpected; what story surrounds the artwork; how the "
        "artist tells that story; how visual details and symbolism "
        "relate to its themes; and what cultural or historical themes "
        "connect it to its period or to modern contexts."
    ),
    (
        "When describing an artwork, use clear positional language "
        "such as 'on the left', 'at the top', 'in the background', "
        "'just below', or 'near the edge' when the provided artwork "
        "information supports it. Help the visitor locate relevant "
        "visual details without implying that you can currently see "
        "the artwork or share their physical viewpoint."
    ),
]


DOCENT_PROMPT_PROFILE = PromptProfile(
    assistant_name="Docent",
    user_name="Visitor",
    assistant_role=DOCENT_ASSISTANT_ROLE,
    behavioural_rules=[
        *CORE_BEHAVIOURAL_RULES,
        *DOCENT_BEHAVIOURAL_RULES,
    ],
)

def build_artwork_context_section(
    artwork: Artwork,
) -> PromptSection:
    content = f"""
Title: {artwork.title}
Artist: {artwork.artist or "unknown"}
Date: {artwork.date or "unknown"}
Room: {artwork.room or "unknown"}
Description: {artwork.description or "no description available"}
Themes: {", ".join(artwork.themes) if artwork.themes else "no themes available"}
""".strip()

    return PromptSection(
        title="Current artwork context",
        content=content,
    )


def build_retrieved_documents_section(
    retrieved_documents: list[RetrievedDocument],
) -> PromptSection | None:
    if not retrieved_documents:
        return None

    blocks: list[str] = []

    for index, retrieved in enumerate(retrieved_documents, start=1):
        document = retrieved.document
        metadata = document.metadata

        block = f"""
Retrieved record {index}:
Document ID: {document.document_id}
Reference: {document.source_reference or "unknown"}
Title: {document.title or "unknown"}
Artist: {metadata.get("artist") or "unknown"}
Painting index: {metadata.get("painting_index") or "unknown"}
Inventory number: {metadata.get("inventory_number") or "unknown"}
Retrieval score: {retrieved.score}
Matched fields: {", ".join(retrieved.matched_fields)}
Matched terms: {", ".join(retrieved.matched_terms)}
Snippet: {retrieved.snippet or "no snippet available"}
Document text:
{document.text}
Source URL: {document.url or "no source URL available"}
""".strip()

        blocks.append(block)

    return PromptSection(
        title="Retrieved artwork records",
        content="\n\n".join(blocks),
    )


def build_retrieved_chunks_section(
    retrieved_chunks: list[RetrievedChunk],
) -> PromptSection | None:
    if not retrieved_chunks:
        return None

    blocks: list[str] = []

    for index, retrieved in enumerate(retrieved_chunks, start=1):
        chunk = retrieved.chunk
        metadata = chunk.metadata

        block = f"""
Evidence {index}:
Chunk ID: {chunk.chunk_id}
Chunk type: {chunk.chunk_type}
Parent document ID: {chunk.parent_document_id}
Reference: {chunk.source_reference or "unknown"}
Title: {chunk.title or "unknown"}
Artist: {metadata.get("artist") or "unknown"}
Painting index: {metadata.get("painting_index") or "unknown"}
Inventory number: {metadata.get("inventory_number") or "unknown"}
Source URL: {chunk.url or "no source URL available"}
Retrieval score: {retrieved.score}
Matched terms: {", ".join(retrieved.matched_terms)}
Evidence text:
{chunk.text}
""".strip()

        blocks.append(block)

    return PromptSection(
        title="Retrieved evidence chunks",
        content="\n\n".join(blocks),
    )


def docent_build_prompt(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    artwork: Artwork | None = None,
    retrieved_documents: list[RetrievedDocument] | None = None,
    retrieved_chunks: list[RetrievedChunk] | None = None,
    response_guidance: str | None = None,
) -> str:
    retrieved_documents = retrieved_documents or []
    retrieved_chunks = retrieved_chunks or []

    context_sections: list[PromptSection] = []

    if response_guidance:
        context_sections.append(
            PromptSection(
                title="Response guidance",
                content=response_guidance,
            )
        )

    if artwork is not None:
        context_sections.append(
            build_artwork_context_section(artwork)
        )

    chunk_section = build_retrieved_chunks_section(
        retrieved_chunks
    )
    if chunk_section is not None:
        context_sections.append(chunk_section)

    document_section = build_retrieved_documents_section(
        retrieved_documents
    )
    if document_section is not None:
        context_sections.append(document_section)

    return build_prompt(
        user_input=user_input,
        dialogue_history=dialogue_history,
        profile=DOCENT_PROMPT_PROFILE,
        context_sections=context_sections,
    )
