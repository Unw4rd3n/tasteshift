from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class Category(StrEnum):
    artist = "artist"
    movie = "movie"
    book = "book"

    @property
    def urn(self) -> str:
        return f"urn:entity:{self.value}"


class Level(StrEnum):
    safe = "safe"
    curious = "curious"
    experimental = "experimental"
    wild = "wild"


class Entity(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=500)
    category: Category
    description: str | None = None
    image_url: HttpUrl | None = None
    website_url: HttpUrl | None = None
    tags: list[str] = Field(default_factory=list)


class SignalContribution(BaseModel):
    entity_id: UUID
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class TasteTag(BaseModel):
    id: str = Field(pattern=r"^urn:tag:", max_length=500)
    name: str = Field(min_length=1, max_length=200)
    affinity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class TasteProfile(BaseModel):
    source: Literal["qloo_tag_insights"] = "qloo_tag_insights"
    status: str
    signal_ids: list[UUID]
    tags: list[TasteTag] = Field(default_factory=list, max_length=50)


class Candidate(BaseModel):
    entity: Entity
    affinity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    contributions: list[SignalContribution] = Field(default_factory=list)
    explainability_status: Literal["available", "unavailable", "invalid"] = "unavailable"


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=2, max_length=600)
    categories: list[Category] = Field(
        default_factory=lambda: list(Category), min_length=1, max_length=3
    )

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Describe what you want to explore.")
        return value

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[Category]) -> list[Category]:
        if len(set(value)) != len(value):
            raise ValueError("Choose distinct categories.")
        return value


class DiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed_ids: list[UUID] = Field(min_length=3, max_length=5)
    level: Level = Level.curious
    intent: Intent | None = None

    @model_validator(mode="after")
    def unique_seeds(self):
        if len(set(self.seed_ids)) != len(self.seed_ids):
            raise ValueError("Choose distinct interests.")
        return self


class DiscoveryItem(BaseModel):
    entity: Entity
    explanation: str
    shared_tags: list[str]


class Coverage(BaseModel):
    category: Category
    status: str
    exploration_supported: bool = False


class Evidence(BaseModel):
    id: str
    entity_id: UUID
    source: Literal["qloo_combined_interests"] = "qloo_combined_interests"
    signal_ids: list[UUID]
    shared_tags: list[str]
    contributions: list[SignalContribution] = Field(default_factory=list)
    explainability_status: Literal["available", "unavailable", "invalid"] = "unavailable"
    shared_tags_source: Literal["entity_metadata", "qloo_tag_insights"] = "entity_metadata"


class ExperienceStep(BaseModel):
    entity_id: UUID
    evidence_id: str
    action: Literal["listen", "watch", "read"]
    instruction: str


class AgentResult(BaseModel):
    status: Literal[
        "planned",
        "needs_clarification",
        "insufficient_coverage",
        "fallback_timeout",
        "fallback_budget",
        "fallback_invalid_output",
        "fallback_provider_error",
    ]
    steps: list[ExperienceStep] = Field(default_factory=list)
    question: str | None = None
    missing_categories: list[Category] = Field(default_factory=list)
    model_name: str | None = None
    prompt_version: str = "experience-v1"
    model_requests: int = 0
    tool_calls: int = 0
    qloo_attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class Discovery(BaseModel):
    id: UUID
    level: Level
    items: list[DiscoveryItem]
    coverage: list[Coverage]
    data_mode: str = "live"
    explanation_mode: str = "factual"
    policy_version: str = "rank-tags-v2"
    taste_profile: TasteProfile | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    agent: AgentResult | None = None


class FeedbackAction(StrEnum):
    save = "save"
    not_for_me = "not_for_me"
    already_know = "already_know"


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: UUID
    action: FeedbackAction
