from pydantic import BaseModel, Field

from backend_python.conversation_core.schemas.conversation_schemas import DialogueTurn


class PromptSection(BaseModel):
    title: str
    content: str


class PromptProfile(BaseModel):
    assistant_name: str = "Assistant"
    user_name: str = "User"
    assistant_role: str = "You are a helpful conversational AI assistant."
    behavioural_rules: list[str] = Field(default_factory=list)