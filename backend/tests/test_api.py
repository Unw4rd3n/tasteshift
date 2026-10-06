import asyncio

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from tasteshift.config import Settings
from tasteshift.main import create_app
from tasteshift.storage import FeedbackRecord


async def discover(client, body, key="first"):
    return await client.post("/api/discoveries", json=body, headers={"Idempotency-Key": key})


async def test_unknown_discovery_filter_is_not_silently_ignored(client, body, fake):
    response = await discover(client, {**body, "duration_max": 90})
    assert response.status_code == 422
    assert not fake.calls


async def test_unknown_feedback_fields_are_rejected(client, body):
    payload = (await discover(client, body)).json()
    response = await client.post(
        f"/api/discoveries/{payload['id']}/feedback",
        json={
            "entity_id": payload["items"][0]["entity"]["id"],
            "action": "save",
            "weight": 100,
        },
    )
    assert response.status_code == 422


async def test_concurrent_feedback_creates_one_record(client, body, app):
    payload = (await discover(client, body)).json()
    entity_id = payload["items"][0]["entity"]["id"]
    replies = await asyncio.gather(
        *[
            client.post(
                f"/api/discoveries/{payload['id']}/feedback",
                json={"entity_id": entity_id, "action": "save"},
            )
            for _ in range(8)
        ]
    )
    assert all(reply.status_code == 200 for reply in replies)
    async with app.state.engine.connect() as db:
        assert await db.scalar(select(func.count()).select_from(FeedbackRecord)) == 1


async def test_health_ready_and_search(client):
    assert (await client.get("/api/health")).status_code == 200
    assert (await client.get("/api/ready")).status_code == 200
    response = await client.get("/api/entities/search", params={"q": "Bowie", "category": "artist"})
    assert response.status_code == 200
    assert response.json()["items"][0]["category"] == "artist"


@pytest.mark.parametrize("query", ["", "a", "  ", "x" * 121])
async def test_search_validates_input(client, fake, query):
    response = await client.get("/api/entities/search", params={"q": query})
    assert response.status_code == 422
    assert not fake.calls


async def test_discovery_persists_and_is_idempotent(client, fake, body):
    response = await discover(client, body)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 6
    assert len(fake.calls) == 4
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "test-key" not in response.text
    assert (await client.get(f"/api/discoveries/{payload['id']}")).json() == payload
    assert (await discover(client, body)).json() == payload
    assert len(fake.calls) == 4
    other_body = {**body, "level": "wild"}
    assert (await discover(client, other_body)).status_code == 409


async def test_session_isolation(app, client, body):
    payload = (await discover(client, body)).json()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8000",
        headers={"Origin": "http://localhost:8000"},
    ) as other:
        assert (await other.get(f"/api/discoveries/{payload['id']}")).status_code == 404
        response = await other.post(
            f"/api/discoveries/{payload['id']}/feedback",
            json={
                "entity_id": payload["items"][0]["entity"]["id"],
                "action": "save",
            },
        )
        assert response.status_code == 404


async def test_feedback_changes_next_discovery(app, client, body):
    first = (await discover(client, body)).json()
    rejected = first["items"][0]["entity"]["id"]
    path = f"/api/discoveries/{first['id']}/feedback"
    feedback = {"entity_id": rejected, "action": "not_for_me"}
    assert (await client.post(path, json=feedback)).status_code == 200
    assert (await client.post(path, json=feedback)).status_code == 200
    async with app.state.engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(FeedbackRecord)) == 1
    second = (await discover(client, body, "second")).json()
    assert rejected not in {item["entity"]["id"] for item in second["items"]}


async def test_partial_provider_failure(client, fake, body):
    fake.fail_category = "movie"
    response = await discover(client, body)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 4
    assert response.json()["coverage"][1]["status"] == "provider_rate_limit"
    assert "private" not in response.text


async def test_all_categories_failed(client, fake, body):
    fake.fail_category = "all"
    response = await discover(client, body)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_rate_limit"


async def test_empty_results_are_reported(client, fake, body):
    fake.empty = True
    response = await discover(client, body)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert all(item["status"] == "empty" for item in response.json()["coverage"])


async def test_invalid_origin_and_duplicate_seeds(client, fake, body):
    response = await client.post(
        "/api/discoveries",
        json=body,
        headers={
            "Origin": "https://unrelated.example",
            "Idempotency-Key": "first",
        },
    )
    assert response.status_code == 403
    assert not fake.calls
    assert (
        await discover(client, {**body, "seed_ids": [body["seed_ids"][0]] * 3})
    ).status_code == 422
    assert (await client.post("/api/discoveries", json=body)).status_code == 422


async def test_unconfigured_provider_returns_clear_error():
    app = create_app(Settings(_env_file=None, qloo_api_key=None))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost:8000",
        ) as client:
            response = await client.get("/api/entities/search", params={"q": "Bowie"})
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "provider_not_configured"


def test_only_hackathon_host_allowed():
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            qloo_base_url="https://unrelated.example",
            qloo_api_key=SecretStr("test-key"),
        )


async def test_feedback_cannot_target_unshown_entity(client, body):
    from uuid import UUID

    payload = (await discover(client, body)).json()
    response = await client.post(
        f"/api/discoveries/{payload['id']}/feedback",
        json={
            "entity_id": str(UUID(int=9999)),
            "action": "save",
        },
    )
    assert response.status_code == 422


async def test_saved_item_is_used_as_positive_signal(client, fake, body):
    payload = (await discover(client, body)).json()
    saved_id = payload["items"][0]["entity"]["id"]
    assert (
        await client.post(
            f"/api/discoveries/{payload['id']}/feedback",
            json={
                "entity_id": saved_id,
                "action": "save",
            },
        )
    ).status_code == 200
    assert (await discover(client, body, "with-save")).status_code == 200
    request = [r for r in fake.calls if r.url.path == "/v2/insights"][-1]
    assert saved_id in request.url.params["signal.interests.entities"].split(",")


async def test_current_feedback_replaces_previous_action(client, body, app):
    payload = (await discover(client, body)).json()
    entity_id = payload["items"][0]["entity"]["id"]
    path = f"/api/discoveries/{payload['id']}/feedback"
    for action in ["save", "already_know"]:
        assert (
            await client.post(path, json={"entity_id": entity_id, "action": action})
        ).status_code == 200
    async with app.state.engine.connect() as connection:
        assert await connection.scalar(select(FeedbackRecord.action)) == "already_know"
