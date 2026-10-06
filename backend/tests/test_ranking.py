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


def test_equal_reference_overlap_disables_novelty():
    pool = candidates()
    for c in pool:
        c.entity.tags = ["familiar", "extra-" + str(c.entity.id)]
    seed = parse_entity(entity(1, tags=["familiar"]))
    safe, supported = rank(pool, [seed], set(), Level.safe)
    wild, _ = rank(pool, [seed], set(), Level.wild)
    assert not supported and safe == wild


def test_missing_tags_are_not_treated_as_surprise():
    pool = candidates()
    pool[2].entity.tags = []
    seed = parse_entity(entity(1, tags=["familiar"]))
    selected, supported = rank(pool, [seed], set(), Level.wild)
    assert supported
    assert all(item.entity.tags for item in selected)


def test_unrelated_tag_volume_does_not_change_novelty_ranking():
    seed = parse_entity(entity(1, tags=["familiar"]))
    pool = candidates()
    before = rank(pool, [seed], set(), Level.wild)[0]
    pool[0].entity.tags += [f"unrelated-{i}" for i in range(300)]
    after = rank(pool, [seed], set(), Level.wild)[0]
    assert [i.entity.id for i in before] == [i.entity.id for i in after]


def test_only_tail_metadata_does_not_remove_baseline():
    pool = candidates()
    for c in pool[:6]:
        c.entity.tags = []
    pool[6].entity.tags = ["familiar"]
    seed = parse_entity(entity(1, tags=["familiar"]))
    result, supported = rank(pool, [seed], set(), Level.wild)
    assert not supported and len(result) == 2
    assert result[0].entity.id == pool[0].entity.id
