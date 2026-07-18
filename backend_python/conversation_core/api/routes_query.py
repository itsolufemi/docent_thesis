from fastapi import APIRouter, Cookie, Response

from conversation_core.schemas.query_schemas import (
    QueryRequest,
    QueryResponse,
)
from conversation_core.services.query_service import QueryEngine
from conversation_core.services.query_service import (
    default_query_engine,
)

CONVERSATION_COOKIE_NAME = "conversation_id"


def create_query_router(
    query_engine: QueryEngine | None = None,
    route_path: str = "/api/query",
) -> APIRouter:
    router = APIRouter()

    active_query_engine = query_engine or default_query_engine

    @router.post(
        route_path,
        response_model=QueryResponse,
    )
    def query(
        request: QueryRequest,
        response: Response,
        conversation_id: str | None = Cookie(
            default=None,
        ),
    ):
        result = active_query_engine.generate_response(
            text=request.text,
            conversation_id=conversation_id,
            subject_reference=request.subject_reference,
            include_debug=request.debug,
        )

        if result.conversation_id is not None:
            response.set_cookie(
                key=CONVERSATION_COOKIE_NAME,
                value=result.conversation_id,
                httponly=True,
                samesite="lax",
                secure=False,
            )

        return QueryResponse(
            request=result.request,
            response=result.response,
            conversation_id=result.conversation_id,
            subject_reference=result.subject_reference,
            sources=result.sources,
            debug=result.debug,
        )

    return router
