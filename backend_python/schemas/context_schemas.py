from typing import Literal
from pydantic import BaseModel

ContextSource = Literal[
    "direct_painting_index",
    "session_current_painting",
    "no_artwork_context",
    "painting_index_not_found",
    "session_not_found"
]

class QueryDebugInfo(BaseModel):
    resolved_painting_index: int | None = None
    context_source: ContextSource
    artwork_context_used: bool
    dialogue_turns_used: int
    prompt: str | None = None


