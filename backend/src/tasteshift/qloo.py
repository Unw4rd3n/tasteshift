import asyncio
from uuid import UUID

import httpx
from pydantic import HttpUrl, TypeAdapter, ValidationError

from tasteshift.domain import Candidate, Category, Entity, SignalContribution, TasteTag


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def safe_url(value) -> HttpUrl | None:
    try:
        return TypeAdapter(HttpUrl).validate_python(value) if value else None
    except ValidationError:
        return None


def parse_contributions(query: dict, seeds: list[UUID]) -> tuple[list[SignalContribution], str]:
    """Optional provider diagnostics must never replace the validated interest set."""
    raw = query.get("explainability")
    if raw is None or (isinstance(raw, dict) and raw.get("warning")):
        return [], "unavailable"
    try:
        rows = raw["signal.interests.entities"]
        if not isinstance(rows, list):
            raise ValueError("Invalid contributions")
        items = [SignalContribution.model_validate(row) for row in rows]
        ids = [item.entity_id for item in items]
        if len(set(ids)) != len(ids) or not set(ids) <= set(seeds):
            raise ValueError("Unknown or duplicate signal")
        return items, "available" if items else "unavailable"
    except (KeyError, TypeError, ValueError, ValidationError):
        return [], "invalid"


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

    async def taste_tags(self, seeds: list[UUID]) -> list[TasteTag]:
        payload = await self.request(
            "/v2/insights",
            {
                "filter.type": "urn:tag",
                "signal.interests.entities": ",".join(map(str, seeds)),
                "take": 50,
            },
        )
        try:
            rows = payload["results"]["tags"]
            if not isinstance(rows, list) or len(rows) > 50:
                raise ValueError("Invalid tags")
            tags = {}
            for row in rows:
                tag = TasteTag(
                    id=row["tag_id"],
                    name=row["name"],
                    affinity=(row.get("query") or {}).get("affinity"),
                )
                # Cultural descriptors only: no audience or demographic inference.
                if tag.id.startswith(
                    ("urn:tag:genre:", "urn:tag:style:", "urn:tag:theme:", "urn:tag:keyword:")
                ):
                    tags.setdefault(tag.id, tag)
            return list(tags.values())
        except (KeyError, AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderError("provider_schema") from exc

    async def candidates(
        self, seeds: list[UUID], category: Category, excluded: set[UUID]
    ) -> list[Candidate]:
        params = {
            "filter.type": category.urn,
            "signal.interests.entities": ",".join(map(str, seeds)),
            "take": 50,
            "feature.explainability": "true",
        }
        if excluded:
            params["filter.exclude.entities"] = ",".join(sorted(map(str, excluded)))
        payload = await self.request("/v2/insights", params)
        results = payload.get("results")
        if not isinstance(results, dict) or not isinstance(results.get("entities"), list):
            raise ProviderError("provider_schema")
        try:
            candidates = []
            for item in results["entities"]:
                query = item.get("query") or {}
                contributions, status = parse_contributions(query, seeds)
                candidates.append(
                    Candidate(
                        entity=parse_entity(item, category),
                        affinity=query.get("affinity"),
                        contributions=contributions,
                        explainability_status=status,
                    )
                )
            return candidates
        except (ValidationError, AttributeError, TypeError) as exc:
            raise ProviderError("provider_schema") from exc
