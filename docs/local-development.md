# Local development

Requirements: Node 22, npm 10+, Python 3.12, uv, and PostgreSQL. Helm is needed for `make helm-check`; Docker and k3d are optional until cluster deployment exists.

1. Create a PostgreSQL database and user named for your own local setup.
2. Copy `.env.example` to `.env`; replace `change-me` and adjust the host/database. Run `set -a; . ./.env; set +a` in your shell. Do not commit `.env`.
3. Run `make install` from the repository root.
4. Run `make frontend` and `make backend` in separate terminals. Open `http://localhost:5173`.
5. Check `curl http://localhost:8000/health/live` and `curl http://localhost:8000/health/ready`.
6. Run `make mcp-woocommerce`, `make mcp-inventory`, or `make mcp-shipping` in separate terminals when testing protocol connections. Endpoints are `http://127.0.0.1:8001/mcp`, `:8002/mcp`, and `:8003/mcp`.

Use `cd backend && uv run --locked alembic current` to inspect migrations. The version directory is empty because no schema exists yet. To run individual checks use `make lint`, `make typecheck`, `make format-check`, `make test`, `make build`, and `make helm-check`. Each Python project has its own `uv.lock`; use `uv lock` inside that project after changing dependencies.
