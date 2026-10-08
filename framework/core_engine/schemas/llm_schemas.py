from pydantic import BaseModel

class LLMStatusResponse(BaseModel):
    reachable: bool
    base_url: str
    configured_model: str
    available_models: list[str]
    message: str 