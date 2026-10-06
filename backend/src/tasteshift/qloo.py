import asyncio
from uuid import UUID

import httpx
from pydantic import HttpUrl, TypeAdapter, ValidationError

from tasteshift.domain import Candidate, Category, Entity


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def safe_url(value) -> HttpUrl | None:
    try:
        return TypeAdapter(HttpUrl).validate_python(value) if value else None
    except ValidationError:
        return None


def parse_entity(raw: dict, category: Category | None = None) -> Entity:
    try:
        # Lookup rows use types; live Insights rows use type + subtype.
        types = raw.get("types")
        subtype = raw.get("subtype")
        if types is None and raw.get("type") == "urn:entity" and isinstance(subtype, str):
            types = [subtype]
        if not isinstance(types, list):
            raise ValueError("Invalid types")
        if subtype is not None and subtype not in types:
            raise ValueError("Conflicting entity types")
        detected = next((kind for kind in Category if kind.urn in types), None)
        if detected is None or (category is not None and category.urn not in types):
            raise ValueError("Unsupported category")
        properties = raw.get("properties") or {}
        image = properties.get("image") or {}
        tags = [tag["id"] for tag in raw.get("tags", []) if isinstance(tag.get("id"), str)]
        return Entity(
            id=raw["entity_id"],
            name=raw["name"],
            category=category or detected,
            description=(
                raw.get("short_description")
                or raw.get("description")
                or properties.get("description")
            ),
            image_url=safe_url(image.get("url")),
            website_url=safe_url(properties.get("website")),
            tags=sorted(set(tags)),
        )
    except (KeyError, TypeError, ValueError, AttributeError, ValidationError) as exc:
        raise ProviderError("provider_schema") from exc


class QlooClient:
    def __init__(self, http: httpx.AsyncClient, key: str | None):
        self.http = http
        self.key = key
        self.semaphore = asyncio.Semaphore(4)

    async def request(self, path: str, params: dict, *, empty_on_404=False) -> dict:
        if not self.key or not self.key.strip():
            raise ProviderError("provider_not_configured")
        try:
            async with self.semaphore:
                response = await self.http.get(path, params=params, headers={"X-Api-Key": self.key})
        except httpx.TimeoutException as exc:
            raise ProviderError("provider_timeout") from exc
        except httpx.RequestError as exc:
            raise ProviderError("provider_unavailable") from exc
        if response.status_code == 404 and empty_on_404:
            return {"results": []}
        if response.status_code in (401, 403):
            raise ProviderError("provider_access")
        if response.status_code == 429:
            raise ProviderError("provider_rate_limit")
        if response.status_code != 200:
            raise ProviderError("provider_unavailable")
        try:
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("success") is False:
                raise ValueError("Invalid response")
            return payload
        except ValueError as exc:
            raise ProviderError("provider_schema") from exc

    async def search(self, query: str, category: Category) -> list[Entity]:
        payload = await self.request(
            "/search", {"query": query, "types": category.urn, "take": 10}, empty_on_404=True
        )
        return self.parse_results(payload, category)

    async def entities(self, ids: list[UUID]) -> list[Entity]:
        payload = await self.request("/entities", {"entity_ids": ",".join(map(str, ids))})
        return self.parse_results(payload)

    @staticmethod
    def parse_results(payload: dict, category: Category | None = None) -> list[Entity]:
        results = payload.get("results")
        if not isinstance(results, list):
            raise ProviderError("provider_schema")
        return [parse_entity(item, category) for item in results]

    async def candidates(
        self, seeds: list[UUID], category: Category, excluded: set[UUID]
    ) -> list[Candidate]:
        params = {
            "filter.type": category.urn,
            "signal.interests.entities": ",".join(map(str, seeds)),
            "take": 50,
        }
        if excluded:
            params["filter.exclude.entities"] = ",".join(sorted(map(str, excluded)))
        payload = await self.request("/v2/insights", params)
        results = payload.get("results")
        if not isinstance(results, dict) or not isinstance(results.get("entities"), list):
            raise ProviderError("provider_schema")
        try:
            return [
                Candidate(
                    entity=parse_entity(item, category),
                    affinity=(item.get("query") or {}).get("affinity"),
                )
                for item in results["entities"]
            ]
        except (ValidationError, AttributeError, TypeError) as exc:
            raise ProviderError("provider_schema") from exc
