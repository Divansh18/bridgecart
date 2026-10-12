# BridgeCart

BridgeCart is a team MCP gateway for WooCommerce. Milestone five adds a React operations dashboard for the existing team API, upstream registry, API keys, and audit logs. LLM chat remains future work.

## Local store

Install Docker Desktop, k3d, kubectl, Helm, and Python 3.12+. From a fresh checkout:

```sh
make store-cluster
make store-secrets
make store-deploy
make store-status
make store-smoke
make mcp-deploy  # creates dedicated API and bearer Secrets, builds/imports image, upgrades Helm
make install  # local locked dependencies for backend verification helpers
make gateway-deploy  # PostgreSQL, migration/admin bootstrap, gateway and demo MCP images
make backend-status
make backend-verify  # isolated migration and access-flow test against PostgreSQL
make backend-live-verify  # live admin/member flow and backend pod replacement
make gateway-verify  # seven tools across three upstreams and two-user audit attribution
make gateway-outage-verify  # controlled shipping outage, then automatic restoration
make gateway-network-verify  # owned temporary Pod tests denied network paths
make dashboard-deploy  # build/import frontend and updated backend; preserve store and PVCs
make dashboard-status
make dashboard-smoke
make dashboard-live-verify  # Playwright admin/member flow; creates deactivated test member
```

Add `127.0.0.1 shop.bridgecart.local api.bridgecart.local app.bridgecart.local` to your hosts file if absent. Open [the storefront](http://shop.bridgecart.local:8088/), [WordPress admin](http://shop.bridgecart.local:8088/wp-admin/), [team API](http://api.bridgecart.local:8088/docs), and [dashboard](http://app.bridgecart.local:8088/). WordPress and BridgeCart have separate admin accounts and Secrets; retrieve credentials privately as described in [local development](docs/local-development.md). No credentials are stored in this repository.

`make store-cluster` checks for an existing cluster and occupied ports before creating anything. It never deletes a cluster. `make store-secrets` preserves an existing Secret. `make store-deploy` runs the Helm bootstrap hook; `make store-bootstrap` runs it again to check idempotency. Optional `make store-images` imports the pinned images into k3d when node pulls are unavailable.

The demo product is **BridgeCart Demo Mug**, SKU `BRIDGECART-DEMO-001`, priced at ₹499. India free shipping and cash on delivery support a test checkout. See [the demo checklist](docs/demo-checklist.md).
The local demo is made public and uses Shop as its homepage on its first bootstrap; production values leave site visibility and the homepage under administrator control.

## Repository

- `frontend/`: React/Vite operations dashboard, deployed through Traefik at `app.bridgecart.local` with same-origin `/api` routing.
- `backend/`: team API, PostgreSQL migrations, admin upstream registry, and MCP gateway at `/mcp`.
- `services/`: WooCommerce, seeded inventory, and deterministic shipping MCP services, each deployed internally.
- `deploy/helm/bridgecart/`: one chart for local k3d and production k3s; values files select environment details.
- `deploy/k3d/cluster.yaml`: pinned local k3s cluster with Traefik and host port 8088.

Run `make check` for existing frontend/backend/MCP checks and Helm lint/template. The local-path PVCs survive pod replacement and are retained on Helm uninstall, but are tied to their k3d node and do not replace backups. Read [architecture](docs/architecture.md), [production](docs/production.md), and the [runbook](docs/runbook.md) before upgrades or cleanup.

For milestone-six preparation, run `make anthropic-secret` in your own interactive terminal to enter `ANTHROPIC_API_KEY` with hidden input. This creates or updates the dedicated local Kubernetes Secret without printing the key. Anthropic injection is opt-in and chat is not implemented; see [local development](docs/local-development.md#anthropic-key-preparation).

Only the backend gateway is exposed at [the local MCP endpoint](http://api.bridgecart.local:8088/mcp). Upstream MCP Services have no public Ingress. The user's gateway API key is separate from each upstream bearer and the WooCommerce REST key. See [gateway setup](docs/local-development.md#gateway-milestone-4b) and [architecture](docs/architecture.md#gateway-milestone-4b).

The team API uses an opaque HttpOnly session cookie and a separate CSRF cookie/header for mutations. Gateway API keys are hashed in PostgreSQL and are never accepted as browser sessions. See [team access setup](docs/local-development.md#team-api-milestone-4a) and [architecture](docs/architecture.md#team-access-milestone-4a).
