from uuid import UUID

import httpx
import pytest

from tasteshift.config import Settings
from tasteshift.discovery import DiscoveryService
from tasteshift.domain import Category, DiscoveryRequest, Level
from tasteshift.qloo import ProviderError, QlooClient, parse_contributions, parse_entity
from tasteshift.ranking import rank

from .conftest import SEEDS, FakeQloo, entity
from .test_api import discover
from .test_ranking import candidates


class ProfileQloo(FakeQloo):
    def __init__(self, status=200, tags=None):
        super().__init__()
        self.status = status
        self.tags = (
            tags
            if tags is not None
            else [
                {
                    "tag_id": "urn:tag:style:qloo:familiar",
                    "name": "Familiar",
                    "query": {"affinity": 0.9},
                },
                {"tag_id": "urn:tag:audience:life_stage:parent", "name": "Parent"},
            ]
        )

    def __call__(self, request):
        if request.url.params.get("filter.type") == "urn:tag":
            self.calls.append(request)
            return httpx.Response(self.status, json={"results": {"tags": self.tags}})
        response = super().__call__(request)
        data = response.json()
        rows = data["results"]
        rows = rows if isinstance(rows, list) else rows["entities"]
        for row in rows:
            if request.url.path == "/entities":
                row["tags"] = []
            else:
                number = UUID(row["entity_id"]).int % 100
                row["tags"] = [
                    {
                        "id": "urn:tag:style:qloo:familiar"
                        if number < 2
                        else "urn:tag:style:qloo:unfamiliar"
                    }
                ]
                row.setdefault("query", {})["explainability"] = {
                    "signal.interests.entities": [{"entity_id": str(SEEDS[0]), "score": 0.7}]
                }
        return httpx.Response(200, json=data)


def test_aggregate_profile_enables_ranking_without_faking_seed_tags():
    seed = parse_entity(entity(1))
    safe, supported = rank(candidates(), [seed], set(), Level.safe, profile_tags={"familiar"})
    wild, _ = rank(candidates(), [seed], set(), Level.wild, profile_tags={"familiar"})
    assert supported and seed.tags == []
    assert safe != wild


async def test_real_shape_profile_and_contributions_are_persisted(agent_client, intent_body):
    provider = ProfileQloo()
    async with agent_client(qloo_handler=provider) as (client, app):
        response = await discover(client, intent_body)
        assert response.status_code == 200
        result = response.json()
        assert result["taste_profile"]["status"] == "ready"
        assert len(result["taste_profile"]["tags"]) == 1
        assert all(c["exploration_supported"] for c in result["coverage"])
        assert result["agent"]["qloo_attempts"] == 5
        assert result["agent"]["status"] == "planned"
        assert all(e["contributions"][0]["entity_id"] == str(SEEDS[0]) for e in result["evidence"])
        assert all(e["shared_tags_source"] == "qloo_tag_insights" for e in result["evidence"])
        assert "relative input contributions from Test 1" in result["items"][0]["explanation"]
        assert (await client.get("/api/discoveries/" + result["id"])).json() == result
        before = len(provider.calls)
        assert (await discover(client, intent_body)).json() == result
        assert len(provider.calls) == before


@pytest.mark.parametrize(
    "status,limit,expected",
    [
        (429, 6, "provider_rate_limit"),
        (200, 4, "provider_budget_exhausted"),
    ],
)
async def test_optional_profile_failure_preserves_recommendations(status, limit, expected):
    provider = ProfileQloo(status=status)
    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com", transport=httpx.MockTransport(provider)
    ) as http:
        result = await DiscoveryService(
            Settings(_env_file=None, qloo_attempt_limit=limit), QlooClient(http, "test")
        ).create(DiscoveryRequest(seed_ids=SEEDS), set(SEEDS), [])
    assert len(result.items) == 6
    assert result.taste_profile.status == expected
    assert not any(c.exploration_supported for c in result.coverage)


async def test_empty_profile_is_explicit():
    provider = ProfileQloo(tags=[])
    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com", transport=httpx.MockTransport(provider)
    ) as http:
        result = await DiscoveryService(Settings(_env_file=None), QlooClient(http, "test")).create(
            DiscoveryRequest(seed_ids=SEEDS), set(SEEDS), []
        )
    assert result.taste_profile.status == "empty"
    assert len(result.items) == 6


@pytest.mark.parametrize(
    "rows",
    [
        [{"entity_id": str(UUID(int=999)), "score": 0.5}],
        [{"entity_id": str(SEEDS[0]), "score": 1.1}],
        [{"entity_id": str(SEEDS[0]), "score": float("nan")}],
        [{"entity_id": str(SEEDS[0]), "score": 0.2}] * 2,
        "invalid",
    ],
)
def test_invalid_optional_explainability_is_not_used(rows):
    assert parse_contributions({"explainability": {"signal.interests.entities": rows}}, SEEDS) == (
        [],
        "invalid",
    )


def test_warning_and_missing_explainability_are_explicit():
    assert parse_contributions({}, SEEDS) == ([], "unavailable")
    assert parse_contributions({"explainability": {"warning": "not computed"}}, SEEDS) == (
        [],
        "unavailable",
    )


@pytest.mark.parametrize("rows", [{}, [None], [{"tag_id": "bad", "name": "bad"}]])
async def test_invalid_tag_response_is_sanitized(rows):
    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"results": {"tags": rows}})
        ),
    ) as http:
        with pytest.raises(ProviderError, match="provider_schema"):
            await QlooClient(http, "test").taste_tags(SEEDS)


async def test_explainability_request_flag(fake):
    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com", transport=httpx.MockTransport(fake)
    ) as http:
        await QlooClient(http, "test").candidates(SEEDS, Category.movie, set(SEEDS))
    assert fake.calls[0].url.params["feature.explainability"] == "true"
