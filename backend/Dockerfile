FROM ghcr.io/astral-sh/uv:0.12.24 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN uv sync --locked --no-dev && useradd --create-home --uid 10001 bridgecart && chown -R bridgecart:bridgecart /app
USER bridgecart
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "bridgecart.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
