from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend_python.conversation_core.api.routes_conversation import router as conversation_router

from backend_python.conversation_core.api.routes_health import router as health_router
from backend_python.conversation_core.api.routes_query import router as query_router
from backend_python.conversation_core.api.routes_llm import router as llm_router
from backend_python.docent.api.routes_artworks import router as artworks_router
from backend_python.retrieval.api.routes_keyword_retrieval import router as retrieval_router
from backend_python.retrieval.api.routes_rag import router as rag_router
from backend_python.retrieval.api.routes_index import router as index_router
from backend_python.retrieval.api.routes_embeddings import router as embeddings_router


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
app.include_router(conversation_router)
app.include_router(retrieval_router)
app.include_router(rag_router)
app.include_router(index_router)
app.include_router(embeddings_router)