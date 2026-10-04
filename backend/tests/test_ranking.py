from uuid import UUID

from tasteshift.domain import Candidate, Level
from tasteshift.qloo import parse_entity
from tasteshift.ranking import rank
from tests.conftest import entity


def candidates():
    return [
        Candidate(
            entity=parse_entity(entity(i + 10, tags=["familiar"] if i < 2 else ["new"])),
            affinity=1 - i * 0.1,
        )
        for i in range(8)
    ]


def test_excludes_seeds_and_deduplicates():
    pool = candidates()
    result, _ = rank(pool + pool, [], {UUID(int=10)}, Level.safe)
    ids = [item.entity.id for item in result]
    assert UUID(int=10) not in ids
    assert len(ids) == len(set(ids)) == 2


def test_wild_selects_more_distant_tags():
    seeds = [parse_entity(entity(1, tags=["familiar"]))]
    safe, supported = rank(candidates(), seeds, set(), Level.safe)
    wild, _ = rank(candidates(), seeds, set(), Level.wild)
    assert supported
    assert all(item.shared_tags == ["familiar"] for item in safe)
    assert all(not item.shared_tags for item in wild)
    assert wild == rank(candidates(), seeds, set(), Level.wild)[0]


def test_missing_metadata_disables_exploration():
    pool = candidates()
    for candidate in pool:
        candidate.entity.tags = []
    safe, supported = rank(pool, [], set(), Level.safe)
    wild, _ = rank(pool, [], set(), Level.wild)
    assert not supported
    assert safe == wild


def test_empty_pool():
    assert rank([], [], set(), Level.wild) == ([], False)
