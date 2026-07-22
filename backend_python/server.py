from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from conversation_core.api.routes_conversation import (
    router as conversation_router,
)
from conversation_core.api.routes_health import router as health_router
from conversation_core.api.routes_llm import router as llm_router
from conversation_core.api.routes_query import create_query_router
from conversation_core.api.routes_trp import router as trp_router
from conversation_core.api.routes_turn_buffer import (
    create_turn_buffer_router,
)
from conversation_core.api.routes_turn_detection import (
    router as turn_detection_router,
)
from conversation_core.api.routes_utterance_router import (
    router as utterance_router,
)

from docent.api.routes_artworks import router as artworks_router
from docent.api.routes_docent_index import router as docent_index_router
from docent.api.routes_docent_retrieval import router as docent_retrieval_router
from docent.services.docent_query_service import docent_query_engine
from docent.api.routes_docent_embeddings import router as docent_embeddings_router
from docent.api.routes_docent_vector import router as docent_vector_router


app = FastAPI(
    title="docent backend",
    version="0.1.0",
)

permitted_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=permitted_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

query_router = create_query_router(
    query_engine=docent_query_engine,
)
turn_buffer_router = create_turn_buffer_router(
    query_engine=docent_query_engine,
)

app.include_router(health_router)
app.include_router(query_router)
app.include_router(llm_router)
app.include_router(artworks_router)
app.include_router(conversation_router)
app.include_router(docent_retrieval_router)
app.include_router(docent_index_router)
app.include_router(docent_embeddings_router)
app.include_router(docent_vector_router)
app.include_router(utterance_router)
app.include_router(trp_router)
app.include_router(turn_detection_router)
app.include_router(turn_buffer_router)
