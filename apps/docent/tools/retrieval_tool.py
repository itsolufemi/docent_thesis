from __future__ import annotations

from core_engine.tools.retrieval_tool import create_retrieval_tool
from extensions.retrieval.schemas.chunk_schemas import VectorRetrievalResult
from apps.docent.services.docent_vector_retrieval_service import (
    retrieve_docent_chunks_by_vector_similarity,
)
from apps.docent.tools.docent_tool_registry import docent_tool_registry
from apps.docent.services.docent_image_service import image_reference_for_painting


DOCENT_RETRIEVAL_DESCRIPTION = (
    "Retrieve Wallace Collection knowledge needed to answer the visitor. "
    "Identify every independent subject whose knowledge is currently needed "
    "and include all subjects already known in one call. When retrieval "
    "returns useful knowledge for a subject, use that result to answer rather "
    "than repeatedly reformulating and retrieving the same information need. "
    "Make another retrieval call only when the visitor's request contains "
    "another distinct subject that still needs knowledge, or when the previous "
    "retrieval did not provide enough information to answer. A subject "
    "discovered only after the first result may therefore be retrieved in a "
    "later call. Preferred example: for 'Compare The Swing and The Rape of "
    "Europa', call once with subjects=['The Swing', 'The Rape of Europa']. "
    "Avoid serial reformulations such as subjects=['p487'] followed by "
    "subjects=['p487 Wallace Collection'] when the first result already "
    "contains useful knowledge for P487. If retrieved evidence contains "
    "image_reference, that is the exact relative image path to pass to "
    "load_image when visual inspection is needed; do not pass the artwork "
    "reference (for example painting:802) as an image path."
)
DOCENT_RETRIEVAL_SUBJECTS_DESCRIPTION = (
    "All currently known artwork, artist, concept, or collection subjects "
    "whose knowledge is needed for this response. Include multiple independent "
    "subjects in the same call when they are already known. Do not invent a "
    "second subject merely to fill the list."
)


def docent_retriever(query: str) -> VectorRetrievalResult:
    result = retrieve_docent_chunks_by_vector_similarity(
        query=query,
        limit=4,
        expand_parent_documents=True,
        use_hybrid_scoring=True,
        apply_confidence_gate=True,
        min_confidence_score=0.45,
    )
    # Enrich the retrieved chunks even when a persisted vector index predates
    # image support. The image path is metadata, not embedding text.
    for item in result.results:
        painting_index = item.chunk.metadata.get("painting_index")
        image_reference = image_reference_for_painting(painting_index)
        if image_reference:
            item.chunk.metadata["image_reference"] = image_reference
    return result


DOCENT_RETRIEVAL_TOOL, retrieve_knowledge = create_retrieval_tool(
    retriever=docent_retriever,
    name="retrieve_knowledge",
    description=DOCENT_RETRIEVAL_DESCRIPTION,
    subjects_description=DOCENT_RETRIEVAL_SUBJECTS_DESCRIPTION,
    max_results=10,
)


docent_tool_registry.register(
    DOCENT_RETRIEVAL_TOOL,
    retrieve_knowledge,
)
