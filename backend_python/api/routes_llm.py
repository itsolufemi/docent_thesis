from fastapi import APIRouter

from schemas.llm_schemas import LLMStatusResponse
from services.llm_service import check_llm_status
router = APIRouter()

@router.get("/llm/status", response_model=LLMStatusResponse)
def get_llm_status():
    status = check_llm_status()
    return LLMStatusResponse(**status)
