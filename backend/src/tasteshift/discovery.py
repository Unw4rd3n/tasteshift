import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid4

from tasteshift.config import Settings
from tasteshift.domain import Category, Coverage, Discovery, DiscoveryRequest, Evidence
from tasteshift.qloo import ProviderError, QlooClient
from tasteshift.ranking import rank


class UnresolvedInterests(Exception):
    pass


@dataclass
class RequestBudget:
    limit: int
    attempts: int = 0

    def reserve(self):
        if self.attempts >= self.limit:
            raise ProviderError("provider_budget_exhausted")
        self.attempts += 1


class BudgetedQloo:
    """A per-discovery budget; failed HTTP attempts consume it too."""

    def __init__(self, client: QlooClient, budget: RequestBudget):
        self.client = client
        self.budget = budget

    async def entities(self, ids):
        self.budget.reserve()
        return await self.client.entities(ids)

    async def candidates(self, seeds, category, excluded):
        self.budget.reserve()
        return await self.client.candidates(seeds, category, excluded)


class DiscoveryService:
    def __init__(self, settings: Settings, qloo: QlooClient, runner=None):
        self.settings = settings
        self.qloo = qloo
        self.runner = runner

    async def create(
        self, body: DiscoveryRequest, excluded: set[UUID], positives: list[UUID]
    ) -> Discovery:
        signal_ids = list(dict.fromkeys(body.seed_ids + positives))[:8]
        provider = BudgetedQloo(self.qloo, RequestBudget(self.settings.qloo_attempt_limit))
        deadline = asyncio.get_running_loop().time() + self.settings.discovery_timeout
        categories = body.intent.categories if body.intent else list(Category)
        try:
            async with asyncio.timeout_at(deadline):
                seeds = await provider.entities(signal_ids)
                if {e.id for e in seeds} != set(signal_ids):
                    raise UnresolvedInterests
                results = await asyncio.gather(
                    *(
                        provider.candidates(signal_ids, category, excluded)
                        for category in categories
                    ),
                    return_exceptions=True,
                )
        except TimeoutError as exc:
            raise ProviderError("provider_timeout") from exc
        discovery = Discovery(id=uuid4(), level=body.level, items=[], coverage=[])
        failures = []
        pools = {}
        seen = set(excluded)
        for category, result in zip(categories, results, strict=True):
            if isinstance(result, ProviderError):
                failures.append(result)
                discovery.coverage.append(Coverage(category=category, status=result.code))
            elif isinstance(result, BaseException):
                raise result
            else:
                # Category is part of the trust boundary, not only a provider hint.
                pools[category] = [c for c in result if c.entity.category == category]
                selected, supported = rank(pools[category], seeds, seen, body.level)
                discovery.items.extend(selected)
                seen.update(item.entity.id for item in selected)
                discovery.coverage.append(
                    Coverage(
                        category=category,
                        status="ok" if selected else "empty",
                        exploration_supported=supported,
                    )
                )
        if len(failures) == len(categories):
            raise failures[0]
        if body.intent:
            discovery.evidence = [
                Evidence(
                    id=f"{discovery.id}:{item.entity.id}",
                    entity_id=item.entity.id,
                    signal_ids=signal_ids,
                    shared_tags=item.shared_tags,
                )
                for item in discovery.items
            ]
            if self.runner is None:
                raise ProviderError("agent_not_configured")
            discovery.agent = await self.runner.run(
                intent=body.intent,
                discovery=discovery,
                seeds=seeds,
                pools=pools,
                excluded=excluded,
                provider=provider,
                deadline=deadline,
            )
        return discovery


def feedback_signals(body: DiscoveryRequest, feedback) -> tuple[set[UUID], list[UUID]]:
    excluded = set(body.seed_ids) | {
        UUID(item.entity_id) for item in feedback if item.action != "save"
    }
    positives = [UUID(item.entity_id) for item in feedback if item.action == "save"]
    return excluded, positives
