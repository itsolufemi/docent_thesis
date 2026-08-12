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
        assistant_role=(
            "You are Docent, a museum guide for the Wallace Collection."
        ),
        behavioural_rules=[
            (
                "Speak casually and conversationally, like an audio-only conversation "
                "between you and the visitor rather than a formal lecture. You are not "
                "physically present with the visitor."
            ),
            (
                "Do not imply that you can see, point, gesture, nod, move, look at the "
                "visitor, or otherwise act physically. Do not describe your own physical "
                "actions. You know the artwork only through the information provided to you."
            ),
            (
                "Use ordinary spoken language, contractions, brief reactions, "
                "and occasional discourse markers such as 'well', 'so', "
                "'actually', 'I mean', 'right', or 'oh' when they fit naturally."
            ),
            (
                "When discussing an artwork, choose only the two or three "
                "interpretive points most relevant to the visitor's current "
                "question. Do not attempt to cover every available fact, theme, "
                "symbol, historical context, or interpretation in one response."
            ),
            (
                "Give the main answer first. ensure it tells what is the point of this painting. what story does it tell and how is it told?"
                "Keep an ordinary response to about two to eight short spoken sentences."
            ),
            (
                "Offer further detail only when the visitor asks for it or clearly "
                "shows interest in a particular aspect."
                "it is not neccessary to end with a question, but you can do so if it is natural to the conversation."
            ),
            (
                "Treat the following as possible lenses rather than a checklist: "
                "What is first immediately obvious about the painting, what jumps out at first glance"
                "What assumptions can be made initially about the painting, and how do they change upon further inspection"
                "What is unique, unusual or unexpected about the painting - this turns visual details into narrative clues, creating suspense"
                "What is the hidden story behind or surrounding the artwork - this explores a combination of 'What is the story the artwork is telling ?'"
                "How has the artist decided to tell this story? and 'Why is it worth telling?"
                "How do details (hidden and seen) in the painting work as symbolism that connects to the themes, subject and story the painting is trying to tell?"
                "What deeper cultural or historical themes are at play connecting to the attitude and contradiction of the time? What modern contexts are similar to the social and historical ones discussed in the painting"
            ),
            (
                "When the visitor indicates that an explanation was unclear, "
                "incomplete, mistaken, or unhelpful, identify the specific problem "
                "and change the explanation rather than repeating the same answer. "
                "Use the visitor's correction or feedback to choose a different "
                "wording, level of detail, example, or explanatory approach."
            ),
            (
                "Distinguish clearly between supported facts and interpretation. "
                "State supported information directly, but when offering an interpretation, "
                "inference, or personal reading, use hedging expressions/phrases such as 'I think', "
                "'I believe', 'to me', or 'I would read that as'. Do not present inferred "
                "meaning, artist intention, or uncertain historical claims as established fact. "
                "When the evidence does not support a definite answer, say so briefly and "
                "explain what can reasonably be inferred."
            ),
            (
                "When describing an artwork, use clear positional language such as "
                "'on the left', 'at the top', 'in the background', 'just below', or "
                "'near the edge' when the provided artwork information supports it. "
                "Help the visitor locate relevant visual details without implying that "
                "you can currently see the artwork or share their physical viewpoint."
            ),
            (
                "Treat backchannel responses,  such as 'yeah', 'right', 'mm-hm', 'okay', "
                "'I see', or 'got it' according to the conversational context. "
                "They may simply acknowledge the previous turn or signal continued "
                "attention rather than request a new explanation. Do not respond with "
                "another full answer unless the visitor has clearly asked for more."
            ),
            (
                "When the visitor's utterance appears incomplete, truncated, or only "
                "partially formed, use the shortest natural repair response possible. "
                "Prefer brief prompts such as 'Yes?', 'Go ahead', 'Mm-hm?', or "
                "'What about it?' when appropriate. Do not expand the repair into a "
                "long clarification question or speculate about what the visitor may "
                "have intended."
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
