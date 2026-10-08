from pydantic import BaseModel, Field


class ClassifierActionDefinition(BaseModel):
    name: str
    description: str
    example_requests: list[str] = Field(default_factory=list)


class RetrievalClassificationPolicy(BaseModel):
    description: str
    retrieve_for: list[str] = Field(default_factory=list)
    do_not_retrieve_for: list[str] = Field(default_factory=list)


class ClassifierDomainProfile(BaseModel):
    domain_name: str
    domain_description: str
    retrieval_policy: RetrievalClassificationPolicy | None = None
    available_actions: list[ClassifierActionDefinition] = Field(
        default_factory=list
    )
