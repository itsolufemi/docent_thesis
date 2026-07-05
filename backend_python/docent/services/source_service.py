from backend_python.conversation_core.schemas.source_schemas import QuerySource
from backend_python.docent.schemas.artwork_schemas import Artwork
from backend_python.extensions.retrieval.schemas.chunk_schemas import RetrievedChunk
from backend_python.extensions.retrieval.schemas.document_schemas import RetrievedDocument


def build_source_from_artwork(
    artwork: Artwork,
    source_type: str = "artwork_context",
) -> QuerySource:
    return QuerySource(
        source_type=source_type,
        title=artwork.title,
        reference=f"painting:{artwork.painting_index}",
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
        },
    )


def build_sources_from_retrieved_documents(
    retrieved_documents: list[RetrievedDocument],
) -> list[QuerySource]:
    sources: list[QuerySource] = []

    for retrieved in retrieved_documents:
        document = retrieved.document

        sources.append(
            QuerySource(
                source_type="retrieved_document",
                title=document.title,
                reference=document.source_reference or document.document_id,
                url=document.url,
                score=retrieved.score,
                snippet=retrieved.snippet,
                metadata={
                    **document.metadata,
                    "document_id": document.document_id,
                    "matched_fields": retrieved.matched_fields,
                    "matched_terms": retrieved.matched_terms,
                },
            )
        )

    return sources


def build_sources_from_retrieved_chunks(
    retrieved_chunks: list[RetrievedChunk],
) -> list[QuerySource]:
    sources: list[QuerySource] = []

    for retrieved in retrieved_chunks:
        chunk = retrieved.chunk

        sources.append(
            QuerySource(
                source_type="retrieved_chunk",
                title=chunk.title,
                reference=chunk.source_reference or chunk.chunk_id,
                url=chunk.url,
                score=retrieved.score,
                snippet=retrieved.snippet or chunk.text,
                metadata={
                    **chunk.metadata,
                    "chunk_id": chunk.chunk_id,
                    "chunk_type": chunk.chunk_type,
                    "parent_document_id": chunk.parent_document_id,
                    "matched_fields": retrieved.matched_fields,
                    "matched_terms": retrieved.matched_terms,
                },
            )
        )

    return sources