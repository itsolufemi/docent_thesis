from fastapi import APIRouter

from docent.services.docent_retrieval_adapter import get_docent_retrieval_chunks
from extensions.retrieval.schemas.index_schemas import (
    RetrievalIndexResponse,
    RetrievalIndexSummaryResponse,
)
from extensions.retrieval.services.index_service import (
    build_retrieval_index,
    summarize_retrieval_index,
)


router = APIRouter()


@router.get("/api/docent/index/rag", response_model=RetrievalIndexResponse)
def read_docent_retrieval_index():
    chunks = get_docent_retrieval_chunks()
    indexed_chunks = build_retrieval_index(chunks)

    return RetrievalIndexResponse(
        chunks=indexed_chunks,
    )


@router.get(
    "/api/docent/index/rag/summary",
    response_model=RetrievalIndexSummaryResponse,
)
def read_docent_retrieval_index_summary():
    chunks = get_docent_retrieval_chunks()
    indexed_chunks = build_retrieval_index(chunks)
    summary = summarize_retrieval_index(indexed_chunks)

    return RetrievalIndexSummaryResponse(**summary)