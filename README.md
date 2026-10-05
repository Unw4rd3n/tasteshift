# TasteShift

An AI agent that helps you discover what you could like next.

TasteShift starts with a few favourite artists, films or books and finds connections across categories using Qloo. Safe → Wild controls how far the selection moves from familiar tags. Explicit feedback changes the next selection.

## Current state

The Python backend supports entity search, discovery, guest sessions, saved selections and feedback. A Pydantic AI agent can inspect candidates, request eligible entity details, and produce a validated introduction plan. Tests cover scripted models and mocked provider responses; a separate evaluation also exercises live Gemini against synthetic Qloo data. The frontend, Qloo explainability integration and public deployment are still pending. No live Qloo request has been verified yet; access is awaiting an API key.

Test provider responses are synthetic and used only in tests. Runtime never silently substitutes fixture recommendations for Qloo.

## Local setup

Requires Python 3.12, uv and Docker Desktop. Run these commands from the repository root:

```sh
docker compose -p tasteshift-dev up -d --wait
cd backend
uv sync --frozen --python 3.12
```

Create `backend/.env` using the variable names in `.env.example`. Leave `QLOO_API_KEY` empty until the hackathon key arrives. Never commit the real key. Development database credentials in Compose are local-only defaults.

```sh
uv run alembic upgrade head
uv run uvicorn tasteshift.main:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000/docs` for the interactive API. `/api/health` checks the process and `/api/ready` checks the database and initial schema. Search returns `provider_not_configured` until a key is supplied.

## API

- `GET /api/entities/search?q=Bowie&category=artist`
- `POST /api/discoveries` with three to five distinct `seed_ids` and a `level` (`safe`, `curious`, `experimental`, `wild`). Send `Origin: http://localhost:8000` and a new `Idempotency-Key` for each new selection.
- `GET /api/discoveries/{id}` with the session cookie returned on discovery creation.
- `POST /api/discoveries/{id}/feedback` with `entity_id` and `action` (`save`, `not_for_me`, `already_know`). Requires the same session cookie and Origin header.

Reusing an idempotency key returns the saved selection; changing its input returns 409. New feedback affects new selections, not already saved results. Missing provider metadata disables tag-distance exploration explicitly through `coverage.exploration_supported`. Factual explanations identify the combined-interest query, not an unverified causal connection to an individual favourite.

## Tests

```sh
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

The default test suite uses a temporary SQLite database. CI runs the same integration tests on PostgreSQL 16 and checks migrations. To run against a local PostgreSQL test database, first create `tasteshift_test`, then set:

```sh
TEST_DATABASE_URL=postgresql+asyncpg://tasteshift:tasteshift@localhost:5432/tasteshift_test uv run pytest -q
```

The suite resets tables in that test database; never point it at data you need. Test database names must end in `_test`.

The [agent evaluation](docs/agent-evaluation.md) contains 28 reproducible scenarios. Its offline cases run in the normal test suite. From `backend`, `uv run python -m tests.agent_eval` prints a per-case report without model calls. `uv run python -m tests.agent_eval --live` explicitly enables live Gemini for eight selected cases, always with synthetic Qloo responses. It consumes quota and may incur charges on a billed Google project. It stops at the first model-provider failure; there are no automatic retries. Use repeatable `--case ID` options to run a smaller selection.

After the Qloo key arrives, run the opt-in live provider check from `backend`:

```sh
RUN_QLOO_LIVE=1 uv run pytest tests/test_live.py -q
```

This calls real Qloo search and cross-category Insights. It is skipped during regular test runs and CI.

## Agent mode

The model adapter uses Gemini Developer API with `gemini-3.5-flash-lite` by default. Create a key in [Google AI Studio](https://aistudio.google.com/apikey) using a **Free Tier project without billing**, then add `GEMINI_API_KEY` to `backend/.env`. `MODEL_NAME` is optional; its default is also shown in `.env.example`. An old `MODEL_API_KEY` does not enable the agent and is not reused as a Gemini key.

This model currently has a [free API tier](https://ai.google.dev/gemini-api/docs/pricing), subject to project quotas. Code cannot detect your billing tier or prevent charges on an already billed Google project. There is no fallback to OpenAI, Vertex AI or another model, and automatic SDK retries are disabled. Free-tier inputs may be used to improve Google's products; do not send sensitive information. See [Gemini setup](docs/gemini-setup.md). `/api/health` reports configuration, not whether credentials or quota work.

Add an optional intent to a normal discovery request:

```json
{
  "seed_ids": ["<confirmed Qloo UUID>", "<confirmed Qloo UUID>", "<confirmed Qloo UUID>"],
  "level": "curious",
  "intent": {
    "text": "A quiet evening with something unfamiliar",
    "categories": ["artist", "movie", "book"]
  }
}
```

Use actual distinct UUIDs from search; the strings above are placeholders. Without an intent, the original deterministic discovery path remains available. With an intent but no configured model, the API returns `503 agent_not_configured` before provider calls.

Responses include `evidence` and an `agent` section with status, steps, model/prompt version and observed usage. Failed validation, provider calls or budgets produce an explicit `fallback_*` status alongside the factual items, with no unvalidated plan. Saved results and idempotent replay do not re-run the model.

See [agent implementation and limitations](docs/agent-implementation.md) before enabling it publicly. It currently inspects cached Qloo pools, not an open-ended search; unsupported free-text requirements are handled by prompting for clarification, not a verified semantic classifier.

After Qloo and Gemini keys are configured, the separate live check is explicitly opt-in. It consumes quota and can incur charges if your Google project has billing enabled:

```sh
cd backend
RUN_AGENT_LIVE=1 uv run pytest tests/test_live.py::test_live_grounded_agent_plan -q
```

To package the API in Docker:

```sh
docker build -t tasteshift-backend:dev .
```

Supply database configuration and the API key at runtime, never as build arguments. Set `COOKIE_SECURE=true` and `APP_ORIGIN` to the exact HTTPS origin for a hosted deployment.

## Implementation notes

Qloo calls use `https://hackathon.api.qloo.com`, `X-Api-Key`, `/search`, `/entities`, and `GET /v2/insights`. Provider errors are sanitized, calls are time-bounded and outgoing concurrency is limited. The standard path makes one entity lookup and three category requests per discovery; agent mode queries requested categories and may make budgeted detail lookups. Account-level provider quotas and session-data cleanup still need to be completed before a public launch.

The first migration stores discovery items inside a JSON snapshot rather than separate item/evidence tables. This keeps the initial slice small; the snapshot can be split when explainability and experience planning are added. FastAPI currently exposes API documentation, not a finished consumer interface.

See [MVP design](docs/mvp-design.md), [architecture](docs/architecture.md), and [agent research and integration plan](docs/agent-design.md).

The isolated [Pydantic AI experiment](research/agent-spike/README.md) remains a small runtime check. The application now has its own agent implementation and integration tests; it does not import the experiment.
