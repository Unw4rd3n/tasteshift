import httpx
import pytest

from tasteshift.domain import Category
from tasteshift.qloo import ProviderError, QlooClient, parse_entity
from tests.conftest import SEEDS, entity


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "provider_access"),
        (403, "provider_access"),
        (429, "provider_rate_limit"),
        (500, "provider_unavailable"),
        (302, "provider_unavailable"),
    ],
)
async def test_status_is_sanitized(status, code):
    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com",
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text="secret details")),
    ) as http:
        with pytest.raises(ProviderError, match=code):
            await QlooClient(http, "test-key").search("Bowie", Category.artist)


async def test_missing_key_does_not_contact_provider():
    def unexpected(request):
        pytest.fail("Provider must not be called")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        with pytest.raises(ProviderError, match="provider_not_configured"):
            await QlooClient(http, None).search("Bowie", Category.artist)


async def test_wire_contract_and_exclusions(fake):
    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com",
        transport=httpx.MockTransport(fake),
    ) as http:
        qloo = QlooClient(http, "test-key")
        await qloo.search("Bowie", Category.artist)
        candidates = await qloo.candidates(SEEDS, Category.movie, set(SEEDS))
    search, insight = fake.calls
    assert search.url.params["query"] == "Bowie"
    assert search.url.params["types"] == "urn:entity:artist"
    assert insight.method == "GET"
    assert insight.headers["X-Api-Key"] == "test-key"
    assert "test-key" not in str(insight.url)
    assert insight.url.params["signal.interests.entities"] == ",".join(map(str, SEEDS))
    assert insight.url.params["filter.exclude.entities"] == ",".join(map(str, SEEDS))
    assert len(candidates) == 8
    assert candidates[0].affinity == 1


async def test_search_404_is_empty():
    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com",
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
    ) as http:
        assert await QlooClient(http, "test-key").search("Nothing", Category.book) == []


@pytest.mark.parametrize("payload", [{}, {"results": {}}, {"success": False}, {"results": [None]}])
async def test_invalid_search_schema(payload):
    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
    ) as http:
        with pytest.raises(ProviderError, match="provider_schema"):
            await QlooClient(http, "test-key").search("Bowie", Category.artist)


async def test_timeout_is_sanitized():
    def timeout(request):
        raise httpx.ReadTimeout("private error", request=request)

    async with httpx.AsyncClient(
        base_url="https://hackathon.api.qloo.com",
        transport=httpx.MockTransport(timeout),
    ) as http:
        with pytest.raises(ProviderError, match="provider_timeout"):
            await QlooClient(http, "test-key").search("Bowie", Category.artist)


def test_unsafe_urls_are_not_exposed():
    raw = entity(1)
    raw["properties"] = {"website": "javascript:alert(1)", "image": {"url": "file:///etc/passwd"}}
    result = parse_entity(raw)
    assert result.website_url is None
    assert result.image_url is None


def test_wrong_category_is_rejected():
    with pytest.raises(ProviderError, match="provider_schema"):
        parse_entity(entity(1, "movie"), Category.artist)
