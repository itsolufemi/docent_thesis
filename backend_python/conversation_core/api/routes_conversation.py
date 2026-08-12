from fastapi import (
    APIRouter,
    Cookie,
    HTTPException,
    Response,
)

from conversation_core.memory.conversation_store import (
    create_conversation,
    get_conversation,
)
from conversation_core.schemas.conversation_schemas import (
    ConversationState,
)
from conversation_core.schemas.introduction_schemas import (
    IntroductionResponse,
)
from conversation_core.services.query_service import (
    QueryEngine,
    default_query_engine,
)
from conversation_core.schemas.introduction_schemas import (
    IntroductionResponse,
)
from conversation_core.services.query_service import (
    QueryEngine,
    default_query_engine,
)


CONVERSATION_COOKIE_NAME = "conversation_id"


def _set_conversation_cookie(
    response: Response,
    conversation_id: str,
) -> None:
    response.set_cookie(
        key=CONVERSATION_COOKIE_NAME,
        value=conversation_id,
        httponly=True,
        samesite="lax",
        secure=False,
    )


def _generate_introduction_response(
    *,
    query_engine: QueryEngine,
    conversation_id: str,
) -> IntroductionResponse:
    if get_conversation(conversation_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    text, generated = query_engine.ensure_introduction(
        conversation_id=conversation_id
    )

    return IntroductionResponse(
        conversation_id=conversation_id,
        text=text,
        generated=generated,
    )


def create_conversation_router(
    query_engine: QueryEngine | None = None,
) -> APIRouter:
    router = APIRouter()
    active_query_engine = (
        query_engine or default_query_engine
    )

    @router.get(
        "/api/conversations/current",
        response_model=ConversationState,
    )
    def read_current_conversation(
        conversation_id: str | None = Cookie(
            default=None,
            alias=CONVERSATION_COOKIE_NAME,
        ),
    ):
        if conversation_id is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No active conversation cookie found."
                ),
            )

        state = get_conversation(conversation_id)

        if state is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

        return state

    @router.post(
        "/api/conversations/current/introduction",
        response_model=IntroductionResponse,
    )
    def introduce_current_conversation(
        response: Response,
        conversation_id: str | None = Cookie(
            default=None,
            alias=CONVERSATION_COOKIE_NAME,
        ),
    ):
        state = (
            get_conversation(conversation_id)
            if conversation_id is not None
            else None
        )

        if state is None:
            state = create_conversation()
            conversation_id = state.conversation_id

        _set_conversation_cookie(
            response,
            conversation_id,
        )

        return _generate_introduction_response(
            query_engine=active_query_engine,
            conversation_id=conversation_id,
        )

    return router


router = create_conversation_router()
