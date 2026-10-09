# Architecture

The browser talks only to the FastAPI backend. The backend will own authentication, members, API keys, server registry, gateway, audit, and chat features. Routes remain thin; feature services hold business logic. The gateway will own upstream MCP connections, discovery, routing, authorization, and auditing. Future chat tool calls must enter the gateway under the authenticated user's identity. Upstream credentials must remain server-side and never appear in frontend responses or bundles.

The three MCP services are separate Python packages and processes. Their Streamable HTTP endpoints are empty protocol surfaces today. They must not be treated as authorized access points in a deployment until gateway controls and network policy exist. The frontend currently has no API calls.

PostgreSQL is the only runtime dependency of the API at this stage. SQLAlchemy provides async sessions; Alembic is wired to empty metadata. No business tables or migrations have been invented. Liveness checks the process; readiness executes `SELECT 1` with a timeout against PostgreSQL. No MCP service dependency is claimed by readiness yet because the API does not use those services.

The intended production platform is k3s, with k3d for local clusters. Dockerfiles exist for each runnable package. The Helm chart currently has metadata and validated values only; it renders no workloads. Deployment and security wiring are milestone two work.
