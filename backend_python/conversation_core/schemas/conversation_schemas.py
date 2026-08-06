from typing import Any

from pydantic import BaseModel, Field, model_validator


class DialogueTurn(BaseModel):
    previous_subject: list[str] = Field(default_factory=list)
    subject: list[str] = Field(default_factory=list)
    reference: list[str] = Field(default_factory=list)
    user: str | None = None
    assistant: str | None = None

    @model_validator(mode="before")
    @classmethod
    def translate_legacy_input(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        translated = dict(value)
        role = translated.pop("role", None)
        content = translated.pop("content", None)
        subjects = translated.pop("subjects", None)

        if subjects is not None and "subject" not in translated:
            translated["subject"] = subjects

        if role == "user" and "user" not in translated:
            translated["user"] = content
        elif role == "assistant" and "assistant" not in translated:
            translated["assistant"] = content

        return translated


class ConversationState(BaseModel):
    conversation_id: str
    dialogue_history: list[DialogueTurn] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class StartConversationResponse(BaseModel):
    conversation_id: str
    state: ConversationState
