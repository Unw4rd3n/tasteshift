# Typed agent experiment

This is an isolated runtime check, not the application agent. It uses synthetic candidate IDs and a scripted `FunctionModel`, with paid model requests disabled. It does not call Qloo, need an API key, or measure recommendation quality.

Python 3.12; Pydantic AI 1.107.7 is pinned by `uv.lock`.

From this directory:

```sh
uv sync --frozen --python 3.12
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

The tests cover tool execution, per-run ID/evidence validation, one output repair, retry exhaustion, tool and request limits, an independent retrieval-attempt budget, and local deadline cancellation. Synthetic models test execution paths, not real model reasoning. No production dependencies are changed by this experiment.

See [agent design](../../docs/agent-design.md) for the proposed integration and live evaluation plan.
