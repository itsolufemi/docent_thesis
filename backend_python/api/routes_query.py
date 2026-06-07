from fastapi import APIRouter
from schemas.query_schemas import QueryRequest, QueryResponse
from services.query_service import generate_basic_response

router = APIRouter()

@router.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest):
    response_text = generate_basic_response(request.text)
    return QueryResponse(
        request=request.text, 
        response=response_text
    )