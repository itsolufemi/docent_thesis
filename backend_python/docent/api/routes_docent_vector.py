from fastapi import APIRouter, Query
from pydantic import BaseModel

from extensions.retrieval.schemas.chunk_schemas import ChunkSearchResponse
from docent.services.docent_vector_retrieval_service import (
    retrieve_docent_chunks_by_vector_similarity,
    summarize_docent_vector_index,
)


class DocentVectorIndexSummaryResponse(BaseModel):
    total_chunks: int
    total_vectors: int
    dimensions: int


router = APIRouter()


@router.get(
    "/api/docent/vector/search",
    response_model=ChunkSearchResponse,
)

def search_docent_chunks_by_vector(
    query: str,
    limit: int = Query(default=8, ge=1, le=20),
    min_score: float = Query(default=0.0, ge=-1.0, le=1.0),
    force_refresh: bool = False,
    expand_parent_documents: bool = True,
    use_hybrid_scoring: bool = True,
    apply_confidence_gate: bool = True,
    min_confidence_score: float = Query(default=0.40, ge=0.0, le=1.0),
):
    retrieval_result = retrieve_docent_chunks_by_vector_similarity(
        query=query,
        limit=limit,
        min_score=min_score,
        force_refresh=force_refresh,
        expand_parent_documents=expand_parent_documents,
        use_hybrid_scoring=use_hybrid_scoring,
        apply_confidence_gate=apply_confidence_gate,
        min_confidence_score=min_confidence_score,
    )
    
    return ChunkSearchResponse(
        query=query,
        results=retrieval_result.results,
        timings=retrieval_result.timings,
    )


@router.get(
    "/api/docent/vector/index/summary",
    response_model=DocentVectorIndexSummaryResponse,
)
def read_docent_vector_index_summary(
    force_refresh: bool = False,
):
    summary = summarize_docent_vector_index(
        force_refresh=force_refresh,
    )

    return DocentVectorIndexSummaryResponse(**summary)
