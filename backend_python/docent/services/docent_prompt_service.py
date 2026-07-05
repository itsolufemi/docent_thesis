from backend_python.conversation_core.schemas.conversation_schemas import DialogueTurn
from backend_python.conversation_core.schemas.prompt_schemas import (
    PromptProfile,
    PromptSection,
)
from backend_python.conversation_core.services.prompt_service import build_prompt
from backend_python.docent.schemas.artwork_schemas import Artwork
from backend_python.extensions.retrieval.schemas.chunk_schemas import RetrievedChunk
from backend_python.extensions.retrieval.schemas.document_schemas import RetrievedDocument


DOCENT_PROMPT_PROFILE = PromptProfile(
    assistant_name="Docent",
    user_name="Visitor",
    assistant_role="You are Docent, a conversational AI museum guide.",
    behavioural_rules=[
        "Speak naturally, as if speaking aloud to a visitor.",
        "Keep your answer brief unless the visitor asks for detail.",
        "Use the supplied context to ground your answer.",
        "Do not invent details that are not supported by the supplied context.",
        "If the supplied context is insufficient, say so briefly.",
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
) -> str:
    retrieved_documents = retrieved_documents or []
    retrieved_chunks = retrieved_chunks or []

    context_sections: list[PromptSection] = []

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