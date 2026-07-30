from pydantic import BaseModel


class IntroductionDefinition(BaseModel):
    prompt: str
    fallback_text: str | None = None
    store_as_dialogue_turn: bool = True


class IntroductionResponse(BaseModel):
    conversation_id: str
    text: str | None
    generated: bool
