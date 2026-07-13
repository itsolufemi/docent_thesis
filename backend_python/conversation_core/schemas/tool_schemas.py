from typing import Any

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """
    Describes a tool that may be presented to an LLM.

    The parameters field contains a JSON Schema describing
    the arguments the model is allowed to provide.
    """

    name: str
    description: str

    parameters: dict[str, Any] = Field(
        default_factory=dict
    )


class ToolCall(BaseModel):
    """
    A structured request from the LLM to execute one tool.
    """

    name: str

    arguments: dict[str, Any] = Field(
        default_factory=dict
    )


class ToolExecutionContext(BaseModel):
    """
    Trusted application context supplied by the server.

    These values are not chosen by the LLM.
    """

    conversation_id: str


class ToolExecutionResult(BaseModel):
    """
    The normalized result returned after executing a tool.
    """

    tool_name: str
    success: bool

    message: str

    data: dict[str, Any] = Field(
        default_factory=dict
    )