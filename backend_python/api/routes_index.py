from fastapi import APIRouter

from schemas.index_schemas import (
    RagIndexResponse,
    RagIndexSummaryResponse,
)
from services.index_service import (
    build_rag_index,
    summarize_rag_index,
)


router = APIRouter()


@router.get("/api/index/rag", response_model=RagIndexResponse)
def read_rag_index():
    indexed_chunks = build_rag_index()

    return RagIndexResponse(
        chunks=indexed_chunks,
    )


@router.get("/api/index/rag/summary", response_model=RagIndexSummaryResponse)
def read_rag_index_summary():
    summary = summarize_rag_index()

    return RagIndexSummaryResponse(**summary)