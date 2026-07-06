from fastapi import APIRouter, Query

from docent.services.docent_retrieval_adapter import get_docent_retrieval_chunks
from extensions.retrieval.schemas.embedding_schemas import (
    EmbeddingIndexResponse,
    EmbeddingIndexSummaryResponse,
    EmbeddingRequest,
    EmbeddingResponse,
)
from extensions.retrieval.services.embedding_service import (
    embed_indexed_chunks,
    generate_embedding,
    summarize_embedded_chunks,
)
from extensions.retrieval.services.index_service import build_retrieval_index
from config import settings


router = APIRouter()


@router.post("/api/embeddings/text", response_model=EmbeddingResponse)
def embed_text(request: EmbeddingRequest):
    embedding = generate_embedding(request.text)

    return EmbeddingResponse(
        text=request.text,
        model=settings.ollama_embedding_model,
        dimensions=len(embedding),
        embedding=embedding,
    )


@router.get(
    "/api/docent/embeddings/index/summary",
    response_model=EmbeddingIndexSummaryResponse,
)
def read_docent_embedding_index_summary(
    limit: int | None = Query(default=5, ge=1, le=50),
):
    chunks = get_docent_retrieval_chunks()
    indexed_chunks = build_retrieval_index(chunks)

    embedded_chunks = embed_indexed_chunks(
        indexed_chunks=indexed_chunks,
        limit=limit,
    )

    summary = summarize_embedded_chunks(embedded_chunks)

    return EmbeddingIndexSummaryResponse(**summary)


@router.get(
    "/api/docent/embeddings/index",
    response_model=EmbeddingIndexResponse,
)
def read_docent_embedding_index(
    limit: int | None = Query(default=3, ge=1, le=20),
):
    chunks = get_docent_retrieval_chunks()
    indexed_chunks = build_retrieval_index(chunks)

    embedded_chunks = embed_indexed_chunks(
        indexed_chunks=indexed_chunks,
        limit=limit,
    )

    return EmbeddingIndexResponse(
        chunks=embedded_chunks,
    )