FROM ghcr.io/astral-sh/uv:0.12.0 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
RUN uv sync --frozen --no-dev
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "tasteshift.main:app", "--host", "0.0.0.0", "--port", "8000"]
