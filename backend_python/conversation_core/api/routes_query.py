from fastapi import APIRouter

from backend_python.conversation_core.schemas.query_schemas import QueryRequest, QueryResponse
from backend_python.conversation_core.services.query_service import generate_basic_response

router = APIRouter()


@router.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest):
    (
        response_text,
        resolved_painting_index,
        sources,
        debug_info,
    ) = generate_basic_response(
        text=request.text,
        painting_index=request.painting_index,
        session_id=request.session_id,
        include_debug=request.debug,
    )

    return QueryResponse(
        request=request.text,
        response=response_text,
        session_id=request.session_id,
        painting_index=resolved_painting_index,
        sources=sources,
        debug=debug_info,
    )