# Backend validation — 4 October 2026

Initial Python backend implemented; frontend, LLM agent and live Qloo validation remain pending.

## Checks completed locally

- Ruff lint: passed.
- Ruff formatting: passed.
- Unit and API integration tests using temporary SQLite: 36 passed, 1 skipped.
- The same suite using PostgreSQL 16 in Docker Desktop: 36 passed, 1 skipped.
- Alembic initial migration applied to the development PostgreSQL database.
- Alembic model/migration comparison: no pending operations.
- Docker runtime image built successfully and started as a non-root user.
- Running container: `/api/health` returned 200, `/api/ready` returned 200.
- Search without a provider key returned 503 with `provider_not_configured`, as expected.
- OpenAPI schema generated with six paths.

The skipped test is an explicit live-provider check. Set the key privately in `backend/.env` and run `RUN_QLOO_LIVE=1 uv run pytest tests/test_live.py -q` from `backend` after access is granted. Successful synthetic-provider tests do not establish that the live provider integration works.

## Tested behavior

Provider authentication headers and documented request parameters; sanitization of provider errors; timeouts; invalid response schemas; missing keys; empty search; safe output URL schemes; category validation; deduplication and exclusions; deterministic exploration; missing tag metadata; guest session ownership; request validation and origin checks; persisted discovery retrieval; idempotency and conflicting inputs; feedback replacement; rejection affecting later discovery; saved items becoming input signals; partial category failures and complete upstream failure.

The local PostgreSQL test suite uses the dedicated `tasteshift_test` database and resets only its application tables. Development data is in `tasteshift`. Tests reject configured database names that do not end in `_test`.

## Remaining before public release

Verify live response schemas and Qloo explainability support; implement the bounded model-powered agent and frontend; add provider quota enforcement and session cleanup; expand concurrency and overall-deadline tests; perform the full browser journey against the hosted application. The current Dockerfile packages the API only.
