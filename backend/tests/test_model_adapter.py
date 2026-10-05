import json

import httpx2
import pytest
from pydantic_ai import models

from tasteshift.config import Settings
from tasteshift.model import gemini_model

from .test_api import discover


@pytest.mark.parametrize("failure", [None, "rate_limit", "server_error", "timeout", "connection"])
async def test_gemini_wire_adapter_is_bounded_and_sanitized(
    monkeypatch, agent_client, intent_body, failure
):
    calls = []

    def mock(request):
        calls.append(request)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.path == "/v1beta/models/gemini-3.5-flash-lite:generateContent"
        payload = json.loads(request.content)
        assert payload["generationConfig"]["maxOutputTokens"] == 1200
        assert "test-key-never-real" not in request.content.decode()
        if failure == "timeout":
            raise httpx2.ReadTimeout("private network details", request=request)
        if failure == "connection":
            raise httpx2.ConnectError("private network details", request=request)
        if failure:
            return httpx2.Response(
                429 if failure == "rate_limit" else 500,
                json={
                    "error": {
                        "code": 429 if failure == "rate_limit" else 500,
                        "message": "private upstream body",
                        "status": "RESOURCE_EXHAUSTED",
                    }
                },
            )
        declarations = [d for t in payload["tools"] for d in t["functionDeclarations"]]
        output_tool = next(t for t in declarations if "NeedsClarification" in t["name"])
        return httpx2.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": output_tool["name"],
                                        "args": {
                                            "question": "Can we ignore streaming availability?"
                                        },
                                    }
                                }
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 30,
                    "candidatesTokenCount": 20,
                    "totalTokenCount": 50,
                },
            },
        )

    # Only this mocked adapter is allowed; there is no real network transport.
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(mock)) as http:
        async with gemini_model(
            Settings(_env_file=None, gemini_api_key="synthetic-key"), http_client=http
        ) as model:
            async with agent_client(model) as (client, app):
                response = await discover(client, intent_body)
                assert response.status_code == 200, response.text
                status = response.json()["agent"]["status"]
                expected = "fallback_provider_error" if failure else "needs_clarification"
                assert status == ("fallback_timeout" if failure == "timeout" else expected)
                assert "private" not in response.text
    assert len(calls) == 1  # SDK retries must not multiply the application budget.


def test_openai_key_does_not_enable_gemini(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "old-openai-key")
    settings = Settings(_env_file=None, gemini_api_key=None)
    assert settings.gemini_api_key is None


def test_default_model_is_gemini():
    assert Settings(_env_file=None).model_name == "gemini-3.5-flash-lite"


@pytest.mark.parametrize(
    "name", ["gpt-4.1-mini", "https://unrelated.example", "google:gemini-test"]
)
def test_non_gemini_identifier_is_rejected(name):
    with pytest.raises(ValueError):
        Settings(_env_file=None, model_name=name)


async def test_missing_gemini_key_prevents_client_creation():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        async with gemini_model(Settings(_env_file=None, gemini_api_key=None)):
            pytest.fail("Unconfigured model was created")


async def test_gemini_full_tool_roundtrip(monkeypatch, agent_client, intent_body):
    calls = []

    def mock(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            parts = [
                {
                    "functionCall": {
                        "name": "get_candidates",
                        "args": {"categories": ["artist", "movie", "book"]},
                    }
                }
            ]
        elif len(calls) == 2:
            parts = [
                {
                    "functionCall": {
                        "name": "get_shortlist",
                        "args": {"categories": ["artist", "movie", "book"]},
                    }
                }
            ]
        else:
            returns = [
                p["functionResponse"]
                for content in payload["contents"]
                for p in content["parts"]
                if "functionResponse" in p
            ]
            shortlist = next(r["response"] for r in returns if r["name"] == "get_shortlist")
            chosen = {item["category"]: item for item in shortlist["items"]}
            declarations = [d for t in payload["tools"] for d in t["functionDeclarations"]]
            name = next(d["name"] for d in declarations if "PlanDraft" in d["name"])
            parts = [
                {
                    "functionCall": {
                        "name": name,
                        "args": {
                            "steps": [
                                {
                                    "entity_id": item["entity_id"],
                                    "evidence_id": item["evidence_id"],
                                    "action": {
                                        "artist": "listen",
                                        "movie": "watch",
                                        "book": "read",
                                    }[category],
                                }
                                for category, item in chosen.items()
                            ]
                        },
                    }
                }
            ]
        return httpx2.Response(
            200,
            json={
                "candidates": [
                    {"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}
                ],
                "usageMetadata": {
                    "promptTokenCount": 30,
                    "candidatesTokenCount": 20,
                    "totalTokenCount": 50,
                },
            },
        )

    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    # Deployment-level Google Cloud settings cannot silently switch the adapter to Vertex.
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://unrelated.example")
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(mock)) as http:
        async with gemini_model(
            Settings(_env_file=None, gemini_api_key="synthetic-key"), http_client=http
        ) as model:
            assert model.client.vertexai is False
            async with agent_client(model) as (client, app):
                response = await discover(client, intent_body)
                assert response.status_code == 200, response.text
                payload = response.json()
                assert payload["agent"]["status"] == "planned"
                assert len(payload["agent"]["steps"]) == 3
                assert payload["agent"]["model_requests"] == 3
                assert payload["agent"]["input_tokens"] == 90
                assert payload["agent"]["output_tokens"] == 60
    assert len(calls) == 3
