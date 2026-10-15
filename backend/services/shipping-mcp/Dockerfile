FROM ghcr.io/astral-sh/uv:0.12.24 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev && useradd --create-home --uid 10001 bridgecart && chown -R bridgecart:bridgecart /app
USER bridgecart
EXPOSE 8003
ENV SHIPPING_MCP_HOST=0.0.0.0
CMD ["/app/.venv/bin/python", "-m", "shipping_mcp.server"]
