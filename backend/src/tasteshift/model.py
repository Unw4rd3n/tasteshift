from contextlib import asynccontextmanager

from google.genai import Client, types
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from tasteshift.config import Settings


@asynccontextmanager
async def gemini_model(settings: Settings, *, http_client=None):
    if settings.gemini_api_key is None:
        raise ValueError("Configure GEMINI_API_KEY before creating a model client")
    client = Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        vertexai=False,
        http_options=types.HttpOptions(
            base_url="https://generativelanguage.googleapis.com",
            api_version="v1beta",
            timeout=int(settings.discovery_timeout * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
            httpx_async_client=http_client,
        ),
    )
    try:
        yield GoogleModel(settings.model_name, provider=GoogleProvider(client=client))
    finally:
        await client.aio.aclose()
        client.close()
