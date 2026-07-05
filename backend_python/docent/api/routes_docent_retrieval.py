from fastapi import APIRouter, Query

from backend_python.docent.services.docent_retrieval_adapter import (
    get_docent_retrieval_chunks,
    get_docent_retrieval_documents,
)
from backend_python.extensions.retrieval.schemas.chunk_schemas import (
    ChunkListResponse,
    ChunkSearchResponse,
)
from backend_python.extensions.retrieval.schemas.document_schemas import (
    RetrievalSearchResponse,
)
from backend_python.extensions.retrieval.services.keyword_retrieval_service import (
    retrieve_documents_by_keyword,
)
from backend_python.extensions.retrieval.services.rag_service import (
    retrieve_chunks_for_query,
)


router = APIRouter()


@router.get("/api/docent/retrieval/search", response_model=RetrievalSearchResponse)
def search_docent_documents(
    query: str,
    limit: int = Query(default=5, ge=1, le=10),
):
    documents = get_docent_retrieval_documents()

    results = retrieve_documents_by_keyword(
        query=query,
        documents=documents,
        limit=limit,
    )

    return RetrievalSearchResponse(
        query=query,
        results=results,
    )


@router.get("/api/docent/rag/chunks", response_model=ChunkListResponse)
def list_docent_chunks():
    return ChunkListResponse(
        chunks=get_docent_retrieval_chunks(),
    )


@router.get("/api/docent/rag/search", response_model=ChunkSearchResponse)
def search_docent_chunks(
    query: str,
    limit: int = Query(default=5, ge=1, le=10),
):
    chunks = get_docent_retrieval_chunks()

    results = retrieve_chunks_for_query(
        query=query,
        chunks=chunks,
        limit=limit,
    )

    return ChunkSearchResponse(
        query=query,
        results=results,
    )