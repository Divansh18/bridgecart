# BridgeCart

BridgeCart is a team MCP gateway project for WooCommerce. Milestone 4A adds a PostgreSQL-backed team API with session login, invitations, member administration, and API-key management. The WooCommerce store and its five-tool MCP service remain deployed. Gateway routing, dashboard features, and chat remain unimplemented.

## Local store

Install Docker Desktop, k3d, kubectl, Helm, and Python 3.12+. From a fresh checkout:

```sh
make store-cluster
make store-secrets
make store-deploy
make store-status
make store-smoke
make mcp-deploy  # creates dedicated API and bearer Secrets, builds/imports image, upgrades Helm
make mcp-verify  # temporary in-cluster client checks auth and tool catalog
make install  # local locked dependencies for backend verification helpers
make backend-deploy  # PostgreSQL PVC, migration/admin bootstrap, backend image and API Ingress
make backend-status
make backend-verify  # isolated migration and access-flow test against PostgreSQL
make backend-live-verify  # live admin/member flow and backend pod replacement
```

Add `127.0.0.1 shop.bridgecart.local api.bridgecart.local` to your hosts file if absent. Open [the storefront](http://shop.bridgecart.local:8088/), [WordPress admin](http://shop.bridgecart.local:8088/wp-admin/), and [team API](http://api.bridgecart.local:8088/docs). WordPress and BridgeCart have separate admin accounts and Secrets; retrieve credentials privately as described in [local development](docs/local-development.md). No credentials are stored in this repository.

`make store-cluster` checks for an existing cluster and occupied ports before creating anything. It never deletes a cluster. `make store-secrets` preserves an existing Secret. `make store-deploy` runs the Helm bootstrap hook; `make store-bootstrap` runs it again to check idempotency. Optional `make store-images` imports the pinned images into k3d when node pulls are unavailable.

The demo product is **BridgeCart Demo Mug**, SKU `BRIDGECART-DEMO-001`, priced at ₹499. India free shipping and cash on delivery support a test checkout. See [the demo checklist](docs/demo-checklist.md).
The local demo is made public and uses Shop as its homepage on its first bootstrap; production values leave site visibility and the homepage under administrator control.

## Repository

- `frontend/`: React/Vite landing screen from milestone one; not deployed by this chart.
- `backend/`: deployed FastAPI team-access API and PostgreSQL migrations.
- `services/`: WooCommerce MCP is deployed internally; inventory and shipping MCP remain disabled.
- `deploy/helm/bridgecart/`: one chart for local k3d and production k3s; values files select environment details.
- `deploy/k3d/cluster.yaml`: pinned local k3s cluster with Traefik and host port 8088.

Run `make check` for existing frontend/backend/MCP checks and Helm lint/template. The local-path PVCs survive pod replacement and are retained on Helm uninstall, but are tied to their k3d node and do not replace backups. Read [architecture](docs/architecture.md), [production](docs/production.md), and the [runbook](docs/runbook.md) before upgrades or cleanup.

The MCP Service has no public Ingress. Its WooCommerce REST key is separate from the bearer token that protects Streamable HTTP. See [local MCP setup](docs/local-development.md#mcp-service), [tool behavior](docs/architecture.md#woocommerce-mcp-tools), and [verification results](docs/demo-checklist.md#milestone-three-verification--2026-10-10).

The team API uses an opaque HttpOnly session cookie and a separate CSRF cookie/header for mutations. Gateway API keys are hashed in PostgreSQL and are never accepted as browser sessions. See [team access setup](docs/local-development.md#team-api-milestone-4a) and [architecture](docs/architecture.md#team-access-milestone-4a).
