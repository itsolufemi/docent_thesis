from fastapi import APIRouter
from config import settings

router = APIRouter()
@router.get("/api/health")

# lesson note: 
# router = apirouter... creates a minirouter
# @router.get add the endpoint to the minirouter
# later server.py with import the mini router and plug it into the main app with app.include_router(router)

def health_check():
    return {
        "status": "ok",
        "service": "backend-python",
        "environment": settings.environment
    }