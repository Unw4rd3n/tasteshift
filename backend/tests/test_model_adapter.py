import json

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic_ai import models
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from .test_api import discover


@pytest.mark.parametrize("failure", [None, "rate_limit", "server_error", "timeout"])
async def test_openai_wire_adapter_is_bounded_and_sanitized(
    monkeypatch, agent_client, intent_body, failure
):
    calls = []

    def mock(request):
        calls.append(request)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        payload = json.loads(request.content)
        assert payload["store"] is False
        assert payload["max_output_tokens"] == 1200
        assert "test-key-never-real" not in request.content.decode()
        if failure == "timeout":
            raise httpx2.ReadTimeout("private network details", request=request)
        if failure:
            return httpx2.Response(
                429 if failure == "rate_limit" else 500,
                json={"error": {"message": "private upstream body", "type": "server_error"}},
            )
        output_tool = next(t for t in payload["tools"] if "NeedsClarification" in t["name"])
        return httpx2.Response(
            200,
            json={
                "id": "resp_mock",
                "object": "response",
                "created_at": 1,
                "model": "gpt-4.1-mini",
                "status": "completed",
                "output": [
                    {
                        "id": "fc_mock",
                        "type": "function_call",
                        "call_id": "call_mock",
                        "name": output_tool["name"],
                        "arguments": json.dumps(
                            {"question": "Can we ignore streaming availability?"}
                        ),
                    }
                ],
                "usage": {"input_tokens": 30, "output_tokens": 20, "total_tokens": 50},
                "parallel_tool_calls": True,
                "tools": payload["tools"],
                "tool_choice": "auto",
            },
        )

    # Only this mocked adapter is allowed; there is no real network transport.
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(mock)) as http:
        async with AsyncOpenAI(
            api_key="synthetic-key",
            base_url="https://api.openai.com/v1",
            max_retries=0,
            http_client=http,
        ) as sdk:
            model = OpenAIResponsesModel("gpt-4.1-mini", provider=OpenAIProvider(openai_client=sdk))
            async with agent_client(model) as (client, app):
                response = await discover(client, intent_body)
                assert response.status_code == 200, response.text
                status = response.json()["agent"]["status"]
                assert status == ("fallback_provider_error" if failure else "needs_clarification")
                assert "private" not in response.text
    assert len(calls) == 1  # SDK retries must not multiply the application budget.
