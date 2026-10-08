from fastapi import APIRouter

from core_engine.schemas.llm_schemas import LLMStatusResponse
from core_engine.services.llm_service import check_llm_status
router = APIRouter()

@router.get("/api/llm/status", response_model=LLMStatusResponse)
def get_llm_status():
    status = check_llm_status()
    return LLMStatusResponse(**status)
