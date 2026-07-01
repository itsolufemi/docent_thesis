from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes_session import router as session_router

from api.routes_health import router as health_router
from api.routes_query import router as query_router
from api.routes_llm import router as llm_router
from api.routes_artworks import router as artworks_router
from api.routes_retrieval import router as retrieval_router
from api.routes_rag import router as rag_router


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

app.include_router(health_router)
app.include_router(query_router)
app.include_router(llm_router)
app.include_router(artworks_router)
app.include_router(session_router)
app.include_router(retrieval_router)
app.include_router(rag_router)