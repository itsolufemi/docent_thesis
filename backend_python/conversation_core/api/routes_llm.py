from fastapi import APIRouter

from conversation_core.schemas.llm_schemas import LLMStatusResponse
from conversation_core.services.llm_service import check_llm_status
router = APIRouter()

@router.get("/api/llm/status", response_model=LLMStatusResponse)
def get_llm_status():
    status = check_llm_status()
    return LLMStatusResponse(**status)
