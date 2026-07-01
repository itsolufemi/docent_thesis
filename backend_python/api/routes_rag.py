from fastapi import APIRouter, Query

from schemas.rag_schemas import (
    RagChunkListResponse,
    RagSearchResponse,
)
from services.rag_service import (
    build_all_evidence_chunks,
    retrieve_evidence_chunks_for_query,
)


router = APIRouter()


@router.get("/api/rag/chunks", response_model=RagChunkListResponse)
def list_rag_chunks():
    chunks = build_all_evidence_chunks()

    return RagChunkListResponse(
        chunks=chunks,
    )


@router.get("/api/rag/search", response_model=RagSearchResponse)
def search_rag_chunks(
    query: str,
    limit: int = Query(default=5, ge=1, le=10),
):
    results = retrieve_evidence_chunks_for_query(
        query=query,
        limit=limit,
    )

    return RagSearchResponse(
        query=query,
        results=results,
    )