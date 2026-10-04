import asyncio
from uuid import UUID

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from spike import Context, make_agent

KNOWN = UUID("00000000-0000-0000-0000-000000000001")
UNKNOWN = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture(autouse=True)
def no_paid_model_requests(monkeypatch):
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)


def output(info, entity_id=KNOWN, evidence_id="evidence-1", duplicate=False):
    item = {"entity_id": str(entity_id), "evidence_id": evidence_id}
    return ModelResponse(
        parts=[
            ToolCallPart(
                info.output_tools[0].name,
                {"selections": [item, item] if duplicate else [item]},
            )
        ]
    )


async def test_tool_then_validated_output():
    calls = 0

    def scripted(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(parts=[ToolCallPart("get_candidates", {})])
        return output(info)

    ctx = Context({KNOWN: "evidence-1"})
    result = await make_agent().run("Choose something", model=FunctionModel(scripted), deps=ctx)
    assert result.output.selections[0].entity_id == KNOWN
    assert ctx.attempts == 1
    assert result.usage.requests == 2


@pytest.mark.parametrize("fault", ["unknown", "evidence", "duplicate", "rejected", "unread"])
async def test_semantic_error_gets_one_repair(fault):
    calls = 0
    ctx = Context({KNOWN: "evidence-1", UNKNOWN: "evidence-2"})
    if fault == "rejected":
        ctx.rejected.add(UNKNOWN)

    def scripted(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(parts=[ToolCallPart("get_candidates", {})])
        if calls == 2:
            if fault == "unread":
                ctx.retrieved.clear()
            return output(
                info,
                entity_id=UNKNOWN if fault in {"unknown", "rejected"} else KNOWN,
                evidence_id="wrong" if fault == "evidence" else "evidence-1",
                duplicate=fault == "duplicate",
            )
        ctx.retrieved.add(KNOWN)
        return output(info)

    if fault == "unknown":
        del ctx.candidates[UNKNOWN]
    result = await make_agent().run("Choose", model=FunctionModel(scripted), deps=ctx)
    assert result.output.selections[0].entity_id == KNOWN
    assert calls == 3


async def test_invalid_output_does_not_retry_forever():
    def scripted(messages, info):
        return output(info, entity_id=UNKNOWN)

    with pytest.raises(UnexpectedModelBehavior, match="retries"):
        await make_agent().run(
            "Choose", model=FunctionModel(scripted), deps=Context({KNOWN: "evidence-1"})
        )


async def test_tool_batch_over_limit_has_no_side_effects():
    def scripted(messages, info):
        return ModelResponse(
            parts=[
                ToolCallPart("get_candidates", {}, tool_call_id="a"),
                ToolCallPart("get_candidates", {}, tool_call_id="b"),
            ]
        )

    ctx = Context({KNOWN: "evidence-1"})
    with pytest.raises(UsageLimitExceeded):
        await make_agent().run(
            "Choose",
            model=FunctionModel(scripted),
            deps=ctx,
            usage_limits=UsageLimits(tool_calls_limit=1),
        )
    assert ctx.attempts == 0


async def test_model_request_limit_stops_loop():
    def scripted(messages, info):
        return ModelResponse(parts=[ToolCallPart("get_candidates", {})])

    ctx = Context({KNOWN: "evidence-1"}, attempt_limit=10)
    with pytest.raises(UsageLimitExceeded, match="request_limit"):
        await make_agent().run(
            "Choose",
            model=FunctionModel(scripted),
            deps=ctx,
            usage_limits=UsageLimits(request_limit=2),
        )
    assert ctx.attempts == 2


async def test_independent_provider_attempt_budget():
    def scripted(messages, info):
        return ModelResponse(parts=[ToolCallPart("get_candidates", {})])

    ctx = Context({KNOWN: "evidence-1"}, attempt_limit=1)
    with pytest.raises(UsageLimitExceeded, match="attempt budget"):
        await make_agent().run("Choose", model=FunctionModel(scripted), deps=ctx)
    assert ctx.attempts == 1


async def test_total_deadline_cancels_waiting_model():
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def stalled(messages, info):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def run():
        async with asyncio.timeout(0.1):
            await make_agent().run(
                "Choose", model=FunctionModel(stalled), deps=Context({KNOWN: "evidence-1"})
            )

    with pytest.raises(TimeoutError):
        await run()
    assert entered.is_set()
    assert cancelled.is_set()
