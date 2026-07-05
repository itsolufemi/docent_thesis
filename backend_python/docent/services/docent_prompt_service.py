from backend_python.conversation_core.schemas.conversation_schemas import DialogueTurn
from backend_python.conversation_core.schemas.prompt_schemas import (
    PromptProfile,
    PromptSection,
)

from backend_python.conversation_core.services.prompt_service import build_prompt
from backend_python.docent.schemas.artwork_schemas import Artwork
from backend_python.extensions.retrieval.schemas.kw_keyword_retrieval_schemas import RetrievedArtwork
from backend_python.extensions.retrieval.schemas.rag_schemas import RetrievedEvidenceChunk

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
    retrieved_artworks: list[RetrievedArtwork],
) -> PromptSection | None:
    if not retrieved_artworks:
        return None

    blocks = []

    for index, retrieved in enumerate(retrieved_artworks, start=1):
        artwork = retrieved.artwork

        block = f"""
Retrieved record {index}:
Painting index: {artwork.painting_index}
Title: {artwork.title}
Artist: {artwork.artist or "unknown"}
School: {getattr(artwork, "school", None) or "unknown"}
Date: {artwork.date or "unknown"}
Object type: {getattr(artwork, "object_type", None) or "unknown"}
Medium: {artwork.medium or "unknown"}
Room: {getattr(artwork, "room_name", None) or artwork.room or "unknown"}
Inventory number: {getattr(artwork, "inventory_number", None) or "unknown"}
Matched fields: {", ".join(retrieved.matched_fields)}
Retrieval score: {retrieved.score}
Snippet: {retrieved.snippet or "no snippet available"}
Description: {artwork.description or "no description available"}
Provenance: {getattr(artwork, "provenance", None) or "no provenance available"}
Record URL: {getattr(artwork, "url", None) or "no source URL available"}
""".strip()

        blocks.append(block)

    return PromptSection(
        title="Retrieved artwork records",
        content="\n\n".join(blocks),
    )

def build_retrieved_chunks_section(
    rag_results: list[RetrievedEvidenceChunk],
) -> PromptSection | None:
    if not rag_results:
        return None

    blocks = []

    for index, retrieved in enumerate(rag_results, start=1):
        chunk = retrieved.chunk

        block = f"""
Evidence {index}:
Chunk ID: {chunk.chunk_id}
Chunk type: {chunk.chunk_type}
Painting index: {chunk.painting_index}
Title: {chunk.title}
Artist: {chunk.artist or "unknown"}
Inventory number: {chunk.inventory_number or "unknown"}
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
    retrieved_artworks: list[RetrievedArtwork] | None = None,
    rag_results: list[RetrievedEvidenceChunk] | None = None,
) -> str:
    retrieved_artworks = retrieved_artworks or []
    rag_results = rag_results or []

    context_sections: list[PromptSection] = []

    if artwork is not None:
        context_sections.append(
            build_artwork_context_section(artwork)
        )

    rag_section = build_retrieved_chunks_section(rag_results)
    if rag_section is not None:
        context_sections.append(rag_section)

    retrieved_section = build_retrieved_documents_section(
        retrieved_artworks
    )
    if retrieved_section is not None:
        context_sections.append(retrieved_section)

    return build_prompt(
        user_input=user_input,
        dialogue_history=dialogue_history,
        profile=DOCENT_PROMPT_PROFILE,
        context_sections=context_sections,
    )