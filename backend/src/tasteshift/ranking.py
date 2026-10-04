from uuid import UUID

from tasteshift.domain import Candidate, DiscoveryItem, Entity, Level

WEIGHTS = {Level.safe: 0.0, Level.curious: 0.2, Level.experimental: 0.45, Level.wild: 0.7}
POOLS = {Level.safe: 0.25, Level.curious: 0.5, Level.experimental: 0.75, Level.wild: 1.0}


def rank(
    candidates: list[Candidate], seeds: list[Entity], excluded: set[UUID], level: Level
) -> tuple[list[DiscoveryItem], bool]:
    unique = {}
    for candidate in candidates:
        if candidate.entity.id not in excluded:
            unique.setdefault(candidate.entity.id, candidate)
    # Qloo response order remains authoritative when affinity metadata is absent.
    available = list(unique.values())
    if available and all(candidate.affinity is not None for candidate in available):
        available.sort(key=lambda c: (-c.affinity, str(c.entity.id)))
    seed_tags = {tag for seed in seeds for tag in seed.tags}
    supported = bool(seed_tags) and bool(available) and all(c.entity.tags for c in available)
    selected: list[DiscoveryItem] = []
    positions = {c.entity.id: i for i, c in enumerate(available)}
    denominator = max(len(available) - 1, 1)
    if supported:
        count = max(2, int(len(available) * POOLS[level]))
        available = available[:count]
        # Keep an affinity-rank floor even in Wild; never equate surprise with the tail.
        available = [c for c in available if 1 - positions[c.entity.id] / denominator >= 0.25]
    while available and len(selected) < 2:

        def score(candidate: Candidate):
            relevance = 1 - positions[candidate.entity.id] / denominator
            tags = set(candidate.entity.tags)
            distance = 1 - len(tags & seed_tags) / len(tags | seed_tags) if supported else 0
            previous_tags = {t for item in selected for t in item.entity.tags}
            repetition = (
                len(tags & previous_tags) / len(tags | previous_tags)
                if tags and previous_tags
                else 0
            )
            weight = WEIGHTS[level] if supported else 0
            return (1 - weight) * relevance + weight * distance - 0.1 * repetition

        chosen = max(available, key=score)
        available.remove(chosen)
        shared = sorted(set(chosen.entity.tags) & seed_tags)
        selected.append(
            DiscoveryItem(
                entity=chosen.entity,
                explanation="Selected from Qloo's results for your chosen interests.",
                shared_tags=shared,
            )
        )
    return selected, supported
