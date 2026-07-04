from fastapi import APIRouter

from backend_python.conversation_core.schemas.query_schemas import (
    QueryRequest,
    QueryResponse,
)
from backend_python.docent.services.docent_query_service import (
    docent_query_engine,
)

router = APIRouter()


@router.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest):
    result = docent_query_engine.generate_response(
        text=request.text,
        conversation_id=request.conversation_id,
        subject_reference=request.subject_reference,
        include_debug=request.debug,
    )

    return QueryResponse(
        request=result.request,
        response=result.response,
        conversation_id=result.conversation_id,
        subject_reference=result.subject_reference,
        sources=result.sources,
        debug=result.debug,
    )