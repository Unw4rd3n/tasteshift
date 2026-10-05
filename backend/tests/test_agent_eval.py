import pytest

from tasteshift.config import Settings

from .agent_eval import CASES, evaluate, offline_model


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
async def test_evaluation_contract(case):
    row = await evaluate(case, Settings(_env_file=None), offline_model(case))
    assert row["passed"], row
