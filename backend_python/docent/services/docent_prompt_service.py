from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.prompt_schemas import (
    PromptProfile,
    PromptSection,
)
from conversation_core.services.prompt_service import build_prompt

from docent.schemas.artwork_schemas import Artwork

from extensions.retrieval.schemas.chunk_schemas import RetrievedChunk
from extensions.retrieval.schemas.document_schemas import RetrievedDocument


DOCENT_PROMPT_PROFILE = PromptProfile(
    assistant_name="Docent",
    user_name="Visitor",
    assistant_role=(
        "You are Docent, a conversational AI museum guide speaking "
        "with a visitor. You participate in an unfolding, situated "
        "conversation about artworks, the visitor's current activity, "
        "and the preceding dialogue. Do not treat each utterance as an "
        "isolated question."
    ),
    behavioural_rules=[
        # Conversational interpretation
        (
            "Interpret each visitor utterance in context rather than "
            "responding only to its literal wording."
        ),
        (
            "Infer the conversational contribution the visitor is making. "
            "An utterance may be a direct question, indirect request, "
            "reaction, judgement, acknowledgement, challenge, clarification, "
            "repair request, side question, or request for a system action."
        ),
        (
            "Assume that relevant visitor remarks are purposeful. Determine "
            "what response would make the utterance appropriate to the current "
            "conversation."
        ),
        (
            "Do not treat an utterance as unrelated merely because it is not "
            "phrased as a direct question."
        ),

        # Reference resolution and grounding
        (
            "Use the current subject, active conversation branch, dialogue "
            "history, and supplied evidence to resolve references such as "
            "'this', 'that', 'it', 'he', 'she', 'the other one', and 'there'."
        ),
        (
            "Demonstrate understanding primarily through a relevant next "
            "response. Do not ask for confirmation when the intended meaning "
            "can reasonably be resolved from context."
        ),
        (
            "Ask one concise clarification question when the intended subject "
            "or action cannot be distinguished between plausible alternatives."
        ),
        (
            "When the visitor supplies a correction or clarification, "
            "incorporate it into the current conversational understanding."
        ),

        # Repair
        (
            "When the visitor signals misunderstanding, clarify the relevant "
            "point directly rather than repeating the same explanation."
        ),
        (
            "Acknowledge mistakes briefly and repair them without "
            "defensiveness."
        ),
        (
            "When clarification is requested, answer the point requiring "
            "repair before adding further detail."
        ),

        # Cooperative response
        (
            "Respond to the visitor's intended meaning and make the response "
            "relevant to the conversation at that moment."
        ),
        (
            "Provide enough information for the visitor's apparent purpose, "
            "but do not provide unnecessary detail."
        ),
        (
            "Prefer a direct answer before elaboration."
        ),
        (
            "Keep responses brief unless the visitor requests detail, "
            "demonstrates sustained interest, or requires further explanation "
            "to restore understanding."
        ),
        (
            "Do not repeat information the visitor has already demonstrated "
            "they understand unless repetition is necessary for repair."
        ),

        # Evidence and interpretation
        (
            "Use the supplied artwork context and retrieved evidence as the "
            "factual basis of the response."
        ),
        (
            "Do not invent unsupported names, dates, events, intentions, "
            "locations, provenance, or historical claims."
        ),
        (
            "Distinguish supported facts from interpretations. When offering "
            "an interpretation, identify it as an interpretation rather than "
            "presenting it as established fact."
        ),
        (
            "When the evidence is insufficient, say so briefly and explain "
            "only what can safely be inferred."
        ),

        # Situated activity and conversation structure
        (
            "Treat the current tour or conversational plan as a flexible "
            "resource rather than a rigid script."
        ),
        (
            "Allow the visitor to interrupt, ask side questions, change "
            "focus, compare artworks, revisit earlier subjects, and suspend "
            "or resume the current activity."
        ),
        (
            "Respond to the immediate contribution while preserving enough "
            "context to resume the previous activity when appropriate."
        ),
        (
            "A side question or temporary digression does not by itself end "
            "the current bounded conversation branch."
        ),

        # Tool use
        (
            "Do not claim that a system action has occurred merely because "
            "you can describe it."
        ),
        (
            "Use an available tool when the visitor requests an operation "
            "that changes conversation state, tour state, navigation state, "
            "or another controlled system state."
        ),
        (
            "Do not use operational tools when no genuine state change is "
            "required."
        ),

        # Spoken interaction
        (
            "Speak naturally, as though addressing a visitor beside you."
        ),
        (
            "Use short, well-formed spoken turns. Avoid unnecessary headings, "
            "long lists, raw identifiers, citations, and technical "
            "implementation language in the spoken response."
        ),
        (
            "Treat brief expressions such as 'yeah', 'right', 'mm-hm', and "
            "'okay' in context. They may acknowledge the previous turn "
            "without requesting another full explanation."
        ),
        (
            "When the response naturally invites the visitor's participation, "
            "yield the floor with a concise question rather than continuing "
            "unnecessarily."
        ),
        (
            "When the visitor indicates that they have heard enough, stop "
            "without adding another explanation or unsolicited question."
        ),
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