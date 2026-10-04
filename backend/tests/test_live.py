import os

import httpx
import pytest

from tasteshift.config import Settings
from tasteshift.domain import Category
from tasteshift.qloo import QlooClient


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
