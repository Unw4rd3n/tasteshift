import json
import os

import httpx
import pytest

from tasteshift.config import Settings
from tasteshift.domain import Category
from tasteshift.qloo import QlooClient


@pytest.mark.skipif(os.environ.get("RUN_QLOO_LIVE") != "1", reason="Live Qloo check is opt-in")
async def test_live_profile_explainability_and_exploration():
    from tasteshift.domain import Level
    from tasteshift.ranking import rank

    settings = Settings()
    assert settings.qloo_api_key
    async with httpx.AsyncClient(
        base_url=settings.qloo_base_url, timeout=settings.qloo_timeout, follow_redirects=False
    ) as http:
        qloo = QlooClient(http, settings.qloo_api_key.get_secret_value())
        ids = [
            (await qloo.search(name, Category.artist))[0].id
            for name in ["David Bowie", "Radiohead", "Bjork"]
        ]
        seeds = await qloo.entities(ids)
        tags = await qloo.taste_tags(ids)
        assert tags, "Example profile returned no cultural tags"
        ref = {tag.id for tag in tags}
        summary = {"profile_tags": len(tags), "categories": []}
        for category in Category:
            pool = await qloo.candidates(ids, category, set(ids))
            modes = []
            for level in Level:
                items, supported = rank(pool, seeds, set(ids), level, profile_tags=ref)
                assert len({i.entity.id for i in items}) == len(items)
                assert not {i.entity.id for i in items}.intersection(ids)
                modes.append(
                    {
                        "level": level.value,
                        "supported": supported,
                        "names": [i.entity.name for i in items],
                    }
                )
            for candidate in pool:
                assert {c.entity_id for c in candidate.contributions} <= set(ids)
            summary["categories"].append(
                {
                    "category": category.value,
                    "modes": modes,
                    "explainability_available": sum(
                        c.explainability_status == "available" for c in pool
                    ),
                }
            )
        print(json.dumps(summary, ensure_ascii=False))


@pytest.mark.skipif(os.environ.get("RUN_AGENT_LIVE") != "1", reason="Live agent check is opt-in")
async def test_live_grounded_agent_plan(monkeypatch):
    from pydantic_ai import models

    from tasteshift.agent import AgentRunner
    from tasteshift.discovery import DiscoveryService
    from tasteshift.domain import DiscoveryRequest, Intent
    from tasteshift.model import gemini_model

    settings = Settings()
    assert settings.qloo_api_key, "Configure QLOO_API_KEY before running this live check"
    assert settings.gemini_api_key, "Configure GEMINI_API_KEY before running this live check"
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    async with httpx.AsyncClient(
        base_url=settings.qloo_base_url, timeout=settings.qloo_timeout, follow_redirects=False
    ) as http:
        qloo = QlooClient(http, settings.qloo_api_key.get_secret_value())
        ids = []
        for name in ["David Bowie", "Radiohead", "Bjork"]:
            artists = await qloo.search(name, Category.artist)
            assert artists, "A live interest search was empty"
            ids.append(artists[0].id)
        assert len(set(ids)) == 3
        async with gemini_model(settings) as model:
            service = DiscoveryService(settings, qloo, AgentRunner(settings, model))
            result = await service.create(
                DiscoveryRequest(
                    seed_ids=ids,
                    intent=Intent(text="Introduce me to unfamiliar music, a film and a book"),
                ),
                set(ids),
                [],
            )
            assert result.agent and result.agent.status == "planned", (
                "Live agent did not produce a validated plan; inspect coverage and sanitized status"
            )
            allowed = {item.entity.id for item in result.items}
            assert all(step.entity_id in allowed for step in result.agent.steps)
            assert not allowed.intersection(ids)
            evidence = {item.id: item.entity_id for item in result.evidence}
            assert all(evidence[step.evidence_id] == step.entity_id for step in result.agent.steps)
            entities = {item.entity.id: item.entity for item in result.items}
            assert {entities[step.entity_id].category for step in result.agent.steps} == set(
                Category
            )
            assert len(result.agent.steps) == 3
            assert result.agent.model_requests <= settings.agent_request_limit
            assert result.agent.qloo_attempts <= settings.qloo_attempt_limit


@pytest.mark.skipif(os.environ.get("RUN_QLOO_LIVE") != "1", reason="Live Qloo check is opt-in")
async def test_live_search_and_cross_category_insights():
    settings = Settings()
    assert settings.qloo_api_key and settings.qloo_api_key.get_secret_value().strip(), (
        "Configure QLOO_API_KEY in backend/.env before running live checks"
    )
    async with httpx.AsyncClient(
        base_url=settings.qloo_base_url,
        timeout=settings.qloo_timeout,
        follow_redirects=False,
    ) as http:
        qloo = QlooClient(http, settings.qloo_api_key.get_secret_value())
        artists = await qloo.search("David Bowie", Category.artist)
        assert artists, "Live search returned no artists"
        seeds = [artists[0].id]
        results = await qloo.candidates(seeds, Category.movie, set(seeds))
        assert results, "Live cross-category query returned no movies"
        assert all(item.entity.category == Category.movie for item in results)
