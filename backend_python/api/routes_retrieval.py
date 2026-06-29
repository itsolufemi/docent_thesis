from fastapi import APIRouter, Query

from schemas.retrieval_schemas import RetrievalSearchResponse
from services.retrieval_service import retrieve_artworks_for_query

router = APIRouter()

@router.get("/api/retrieval/search", response_model=RetrievalSearchResponse)
def search_retrieval(
    query:str,
    limit: int = Query(default=5, ge=1, le=10),
):
    results = retrieve_artworks_for_query(
        query=query, 
        limit=limit
    )

    return RetrievalSearchResponse(
        query=query,
        results=results
    )