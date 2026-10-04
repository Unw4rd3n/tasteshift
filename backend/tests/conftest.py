import os
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from pydantic_ai import models

from tasteshift.config import Settings
from tasteshift.main import create_app
from tasteshift.storage import Base

SEEDS = [UUID(int=i) for i in range(1, 4)]


@pytest.fixture(autouse=True)
def no_paid_model_calls(monkeypatch):
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)


def entity(number, category="artist", tags=None):
    return {
        "entity_id": str(UUID(int=number)),
        "name": f"Test {number}",
        "types": [f"urn:entity:{category}"],
        "tags": [{"id": tag} for tag in (tags or [])],
        "properties": {"image": {"url": "https://images.qloo.com/test.jpg"}},
    }


class FakeQloo:
    """Synthetic wire responses, not recordings of the live provider."""

    def __init__(self):
        self.calls = []
        self.fail_category = None
        self.empty = False

    def __call__(self, request):
        self.calls.append(request)
        if request.url.path == "/search":
            category = request.url.params["types"].split(":")[-1]
            return httpx.Response(200, json={"results": [entity(1, category)]})
        if request.url.path == "/entities":
            ids = request.url.params["entity_ids"].split(",")
            return httpx.Response(
                200,
                json={
                    "results": [
                        entity(
                            UUID(id).int,
                            "book"
                            if UUID(id).int >= 300
                            else ("movie" if UUID(id).int >= 200 else "artist"),
                            tags=["urn:tag:test:familiar"],
                        )
                        for id in ids
                    ]
                },
            )
        category = request.url.params["filter.type"].split(":")[-1]
        if self.fail_category in (category, "all"):
            return httpx.Response(429, text="private upstream details")
        base = {"artist": 100, "movie": 200, "book": 300}[category]
        results = (
            []
            if self.empty
            else [
                {
                    **entity(
                        base + i,
                        category,
                        ["urn:tag:test:familiar"] if i < 2 else ["urn:tag:test:unfamiliar"],
                    ),
                    "query": {"affinity": 1 - i * 0.1},
                }
                for i in range(8)
            ]
        )
        return httpx.Response(200, json={"results": {"entities": results}})


@pytest.fixture
def fake():
    return FakeQloo()


@pytest.fixture
async def app(tmp_path, fake):
    test_url = os.environ.get("TEST_DATABASE_URL")
    if test_url and not test_url.rstrip("/").endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must point to a dedicated database ending in _test")
    settings = Settings(
        _env_file=None,
        qloo_api_key=SecretStr("test-key-never-real"),
        model_api_key=None,
        model_name=None,
        database_url=SecretStr(
            os.environ.get("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
        ),
    )
    application = create_app(settings, httpx.MockTransport(fake))
    async with application.state.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8000",
        headers={"Origin": "http://localhost:8000"},
    ) as client:
        yield client


@pytest.fixture
def body():
    return {"seed_ids": list(map(str, SEEDS)), "level": "curious"}


@pytest.fixture
def intent_body(body):
    return {**body, "intent": {"text": "A quiet evening with something unfamiliar"}}


@pytest.fixture
def agent_client(app, fake):
    from .test_agent import scripted_model

    @asynccontextmanager
    async def start(model=None, **overrides):
        settings = Settings(
            _env_file=None,
            qloo_api_key=app.state.qloo.key,
            model_api_key=None,
            model_name=None,
            database_url=app.state.engine.url.render_as_string(hide_password=False),
            **overrides,
        )
        application = create_app(
            settings, httpx.MockTransport(fake), agent_model=model or scripted_model()
        )
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application),
                base_url="http://localhost:8000",
                headers={"Origin": "http://localhost:8000"},
            ) as client:
                yield client, application

    return start
