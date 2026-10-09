# BridgeCart

BridgeCart is a team MCP gateway for WooCommerce, intended for Kubernetes. This first milestone is a runnable project foundation, **not a deployable gateway**.

## Repository

- `frontend/`: React, TypeScript, Vite, Tailwind CSS and shadcn/ui landing screen.
- `backend/`: FastAPI configuration, JSON logging, database sessions, Alembic, and health checks.
- `services/`: three independent, empty MCP servers using Streamable HTTP.
- `deploy/`: Helm chart metadata, values and schema, plus a local k3d cluster definition. The chart emits no workloads yet.

## Quick start

Install Node 22, Python 3.12, uv, PostgreSQL, and optionally Helm. Copy `.env.example` to `.env` and set `BRIDGECART_DATABASE_URL` to a local PostgreSQL URL using `postgresql+asyncpg`. Export those variables in your shell before starting the backend (or copy `.env` into `backend/.env`).

```sh
make install
make frontend
make backend
```

Visit `http://localhost:5173`. The API is at `http://localhost:8000`; `/health/live` returns 200 while the process runs, and `/health/ready` returns 200 only when PostgreSQL responds to `SELECT 1`. Without PostgreSQL it returns 503.

The MCP servers can be started separately with `make mcp-woocommerce`, `make mcp-inventory`, and `make mcp-shipping`. They listen on loopback ports 8001, 8002, and 8003 at `/mcp` and intentionally advertise zero tools.

Run `make check` for lint, type, format, test, frontend build and Helm scaffold validation. See [local development](docs/local-development.md) for exact setup and [architecture](docs/architecture.md) for boundaries.

## Milestone boundary

Authentication, membership, API keys, gateway routing and upstream authorization, audit persistence, chat execution, WooCommerce/inventory/shipping tools, WordPress provisioning, and Kubernetes workload manifests are planned for milestone two. No real secrets belong in this repository.
