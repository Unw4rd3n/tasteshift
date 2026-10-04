from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator


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


class Candidate(BaseModel):
    entity: Entity
    affinity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class DiscoveryRequest(BaseModel):
    seed_ids: list[UUID] = Field(min_length=3, max_length=5)
    level: Level = Level.curious

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


class Discovery(BaseModel):
    id: UUID
    level: Level
    items: list[DiscoveryItem]
    coverage: list[Coverage]
    data_mode: str = "live"
    explanation_mode: str = "factual"
    policy_version: str = "rank-tags-v1"


class FeedbackAction(StrEnum):
    save = "save"
    not_for_me = "not_for_me"
    already_know = "already_know"


class FeedbackRequest(BaseModel):
    entity_id: UUID
    action: FeedbackAction
