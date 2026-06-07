from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings

app = FastAPI(
    title = "docent backend",
    version = "0.1.0"
)

permitted_origins = [ #clientside origins
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=permitted_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    text: str

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "backend-python",
        "environment": settings.environment
    }

@app.post("/api/query")
def query(request: QueryRequest):
    return {
        "request": request.text,
        "response": f"echo: {request.text}"
    }