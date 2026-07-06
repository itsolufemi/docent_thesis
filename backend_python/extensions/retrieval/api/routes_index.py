from fastapi import APIRouter

from extensions.retrieval.schemas.index_schemas import (
    RetrievalIndexResponse,
    RetrievalIndexSummaryResponse,
)
from extensions.retrieval.services.index_service import (
    build_rag_index,
    summarize_rag_index,
)


router = APIRouter()


@router.get("/api/index/rag", response_model=RetrievalIndexResponse)
def read_rag_index():
    indexed_chunks = build_rag_index()

    return RetrievalIndexResponse(
        chunks=indexed_chunks,
    )


@router.get("/api/index/rag/summary", response_model=RetrievalIndexSummaryResponse)
def read_rag_index_summary():
    summary = summarize_rag_index()

    return RetrievalIndexSummaryResponse(**summary)