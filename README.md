# BridgeCart

BridgeCart is a team MCP gateway project for WooCommerce. Milestone two runs a **single-replica WooCommerce demo store** on local k3d: WordPress, MariaDB, Traefik Ingress, PVCs, NetworkPolicies, and an idempotent bootstrap Job. The gateway, authentication, chat, and MCP business tools are still unimplemented.

## Local store

Install Docker Desktop, k3d, kubectl, Helm, and Python 3.12+. From a fresh checkout:

```sh
make store-cluster
make store-secrets
make store-deploy
make store-status
make store-smoke
```

Add `127.0.0.1 shop.bridgecart.local` to your hosts file if it is absent. Open [the storefront](http://shop.bridgecart.local:8088/) and [WordPress admin](http://shop.bridgecart.local:8088/wp-admin/). The admin username is `bridgecart-admin`; retrieve its generated password privately from the local Kubernetes Secret as described in [local development](docs/local-development.md). No credentials are stored in this repository.

`make store-cluster` checks for an existing cluster and occupied ports before creating anything. It never deletes a cluster. `make store-secrets` preserves an existing Secret. `make store-deploy` runs the Helm bootstrap hook; `make store-bootstrap` runs it again to check idempotency. Optional `make store-images` imports the pinned images into k3d when node pulls are unavailable.

The demo product is **BridgeCart Demo Mug**, SKU `BRIDGECART-DEMO-001`, priced at ₹499. India free shipping and cash on delivery support a test checkout. See [the demo checklist](docs/demo-checklist.md).
The local demo is made public on its first bootstrap; production values leave WooCommerce's site visibility under administrator control.

## Repository

- `frontend/`: React/Vite landing screen from milestone one; not deployed by this chart.
- `backend/`: FastAPI foundation from milestone one; not deployed by this chart.
- `services/`: three empty MCP servers from milestone one; not deployed by this chart.
- `deploy/helm/bridgecart/`: one chart for local k3d and production k3s; values files select environment details.
- `deploy/k3d/cluster.yaml`: pinned local k3s cluster with Traefik and host port 8088.

Run `make check` for existing frontend/backend/MCP checks and Helm lint/template. The local-path PVCs survive pod replacement and are retained on Helm uninstall, but are tied to their k3d node and do not replace backups. Read [architecture](docs/architecture.md), [production](docs/production.md), and the [runbook](docs/runbook.md) before upgrades or cleanup.
