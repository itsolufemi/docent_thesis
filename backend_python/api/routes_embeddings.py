from fastapi import APIRouter, Query

from config import settings

from schemas.embedding_schemas import (
    EmbeddingRequest,
    EmbeddingResponse,
    RagEmbeddingIndexSummaryResponse,
)
from services.embedding_service import (
    build_rag_embedding_index,
    generate_embedding,
    summarize_rag_embedding_index,
)


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
    "/api/embeddings/rag-index/summary",
    response_model=RagEmbeddingIndexSummaryResponse,
)
def read_rag_embedding_index_summary(
    limit: int | None = Query(default=5, ge=1, le=50),
):
    summary = summarize_rag_embedding_index(limit=limit)

    return RagEmbeddingIndexSummaryResponse(**summary)


@router.get("/api/embeddings/rag-index")
def read_rag_embedding_index(
    limit: int | None = Query(default=3, ge=1, le=20),
):
    embedded_chunks = build_rag_embedding_index(limit=limit)

    return {
        "chunks": embedded_chunks,
    }