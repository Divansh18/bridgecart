# BridgeCart

BridgeCart is a team MCP gateway for a WooCommerce store on Kubernetes. A React dashboard provides team login, invitations, API-key management, upstream status and tool schemas, audit logs, and optional Claude chat. External MCP clients use one public gateway URL and an individual team API key. Dashboard chat executes tools through that same gateway as the signed-in user; neither upstream credentials nor the Anthropic key reach the browser.

## Architecture

| Component | Responsibility |
| --- | --- |
| `frontend/` | React, TypeScript, Vite, Tailwind CSS, and local shadcn/ui-style components; same-origin `/api` calls and a public gateway URL in runtime configuration. |
| `backend/` | Python 3.12/FastAPI team API, opaque cookie sessions and CSRF, SQLAlchemy/PostgreSQL/Alembic, encrypted upstream registry, official Python MCP SDK Streamable HTTP gateway, user-attributed audit, and Anthropic SDK Claude tool loop. Dependencies are locked with `uv`. |
| `backend/services/woocommerce-mcp/` | Independent MCP project with five product/order tools backed by WooCommerce REST, with separate REST and MCP credentials. |
| `backend/services/inventory-mcp/`, `backend/services/shipping-mcp/` | Independent MCP projects with read-only **seeded demo data** tools; no store or database access. |
| `deploy/helm/bridgecart/` | One chart for local k3d and production k3s: WordPress/WooCommerce, MariaDB, PostgreSQL, backend, frontend, three internal MCP services, Jobs, Ingresses, PVCs, and NetworkPolicies. |
| `scripts/`, `docs/`, `.github/workflows/` | Local setup and verification commands, design/operations notes, and CI checks. |

Traefik exposes the shop, dashboard, and backend API/gateway. MariaDB, PostgreSQL, and upstream MCP services have internal Services only. The gateway owns tool discovery, routing, authorization, and auditing. See [architecture](docs/architecture.md) and [threat model](docs/threat-model.md).

## Fresh-checkout local setup

Install Docker Desktop, k3d 5.9+, kubectl, Helm 3/4, Node 22/npm, Python **3.12.x**, and `uv` (available on `PATH`). Allow image pulls and the first WooCommerce plugin download. The [k3d configuration](deploy/k3d/cluster.yaml) maps loopback port **8088** to Traefik and **6550** to the Kubernetes API; the cluster setup script checks existing clusters and port conflicts and never deletes a cluster. Local k3s supplies Traefik, NetworkPolicy enforcement, and `local-path` storage. Check Docker is running, then edit `/etc/hosts` with `sudo nano /etc/hosts` and add this entry if it is absent:

```text
127.0.0.1 shop.bridgecart.local api.bridgecart.local app.bridgecart.local
```

From the repository root, in this order:

```sh
make store-cluster       # create/reuse the k3d cluster
make store-secrets       # generate/preserve private local store credentials
make store-deploy        # WordPress, MariaDB, PVCs, WooCommerce bootstrap
make store-smoke
make install             # npm ci and locked uv environments
make mcp-deploy          # provision the dedicated WooCommerce API key; build/import its MCP image
make gateway-deploy      # create/preserve team Secrets; build/import backend and demo MCP images
make anthropic-secret    # optional: hidden prompt for your Anthropic key; needed only for chat
make dashboard-deploy    # build/import frontend and backend; enable the dashboard
make dashboard-status
make dashboard-smoke
```

`make store-images` imports the pinned WordPress, WP-CLI, and MariaDB images into k3d if node pulls are unavailable; PostgreSQL must still be pullable or imported separately. The normal bootstrap still needs HTTPS access to download pinned WooCommerce **11.2.1** on first install. Deploy commands are repeatable and preserve existing Secrets and PVCs. `make store-bootstrap` intentionally reruns the idempotent store Job; it does not reset products or orders. See [local development](docs/local-development.md) for failure handling and separate component workflows.

| Local URL | Use |
| --- | --- |
| <http://shop.bridgecart.local:8088/> | Guest storefront; Shop is the local demo homepage. |
| <http://shop.bridgecart.local:8088/wp-admin/> | WordPress/WooCommerce administration. |
| <http://app.bridgecart.local:8088/> | BridgeCart team dashboard; chat is at `/chat`, Connect at `/connect`. |
| <http://api.bridgecart.local:8088/docs> | Team API reference. |
| <http://api.bridgecart.local:8088/mcp> | Public Streamable HTTP gateway for external clients. |

### Private credentials and daily use

On a fresh installation, the local setup scripts generate distinct random WordPress and team-admin passwords in Kubernetes Secrets. Re-running setup preserves them. The WordPress login is **`bridgecart-admin`**; the dashboard login is **`admin@bridgecart.local`**. Run retrieval commands **in your own terminal**; do not paste the output into chat, logs, files, or Git:

```sh
# WordPress admin password
kubectl --context k3d-bridgecart -n bridgecart get secret bridgecart-store-credentials -o jsonpath='{.data.wordpress-admin-password}' | base64 --decode; printf '\n'

# BridgeCart team admin password
kubectl --context k3d-bridgecart -n bridgecart get secret bridgecart-initial-admin -o jsonpath='{.data.admin-password}' | base64 --decode; printf '\n'
```

For a **local WordPress password reset**, run `make store-admin-rotate`; it generates a new random password, updates the WordPress account and its Secret, and the first retrieval command then shows the new value privately. It does not accept a chosen passphrase. The team-admin Secret is used **only when the account is first created**: changing that Secret or rerunning `make gateway-deploy` does not reset an existing dashboard password. There is no supported dashboard-admin password reset command in this repository. If either password is changed outside its documented workflow, the corresponding Secret may be stale; do not assume its decoded value will log in.

`make anthropic-secret` prompts with terminal echo disabled and creates/updates the dedicated `bridgecart-anthropic-api` Secret without printing the key or putting it in Helm values. It is optional; other features remain available without provider configuration. After rotating it, run `kubectl --context k3d-bridgecart -n bridgecart rollout restart deployment/bridgecart-backend` so the backend reads the new environment value. Never use the WordPress password as a team login. Admins invite members through the dashboard; invitation tokens appear once, expire, and have a [private local handoff workflow](docs/local-development.md#team-api-milestone-4a). Team API keys also appear only once and are stored hashed; copy them into a suitable private client secret store.

For the local checkout demo, open the Shop page as a guest, add **BridgeCart Demo Mug** (`BRIDGECART-DEMO-001`, ₹499), and select India free shipping and cash on delivery. The local bootstrap enables these demo settings and makes the store Live; production values do neither. The dashboard uses HttpOnly session cookies and CSRF protection. Admins manage upstreams and members; members manage their own keys. Chat uses that browser session, shows gateway tool traces, and can call tools from more than one upstream. Inventory and shipping answers are seeded demo data, not live stock or carrier quotes. Review a timed-out write in WooCommerce before asking chat or a client to retry it.

### External MCP clients

Create an individual key on the dashboard's **API keys** page, then configure a Streamable HTTP client with only:

- Gateway URL: `http://api.bridgecart.local:8088/mcp`
- `Authorization: Bearer <YOUR_API_KEY>` supplied through the client's private credential mechanism

Do not give the client an internal upstream URL, WooCommerce REST key, upstream bearer, browser cookie, or Anthropic key. Admins can add public HTTPS MCP servers on port 443 in the dashboard; additional cluster-internal destinations require an exact Helm allowlist and policy entry. The [Connect page](http://app.bridgecart.local:8088/connect) shows a generic placeholder-only example; exact client configuration formats vary. The [external-client verification notes](docs/local-development.md#external-mcp-client-acceptance) describe the locally tested Codex CLI workflow.

Exposed tool names are `bc_` + the upstream's **32-character immutable UUID hex** + `_` + the first **24 SHA-256 hex characters** of its original tool name (60 ASCII characters). This prevents cross-server name collisions and survives server display-name or URL edits. The stateless gateway cannot push a persistent tool-list change notification: explicitly request `tools/list` after a registry change or outage/recovery. Execution still rechecks enabled status and user/key validity, so a cached disabled tool or revoked key fails on the next call. Dashboard chat rediscovers tools each turn.

## Verification

| Command | What it checks |
| --- | --- |
| `make check` | Frontend lint/type/format/tests/build; backend and MCP unit tests; script syntax; local and production Helm lint/template. No live store or provider call. Requires `uv` on `PATH`. |
| `make backend-verify` | Alembic and team/gateway/delegation integration tests in a **temporary isolated real PostgreSQL database**; drops only that test database. |
| `make backend-live-verify` | Live admin/member/session/key flow and backend pod replacement; retains a named demo member and test metadata. |
| `make store-smoke` | Read-only HTTP checks of the deployed store, product, cart, and admin login path; does not complete checkout. |
| `make dashboard-smoke` | Deployed SPA routes, runtime config, and unauthenticated API routing; no login flow. |
| `make gateway-verify` | External SDK connection, three-upstream tool listing/calls, authentication and two-user audit; creates then revokes temporary API keys and adds audit rows. |
| `make gateway-network-verify` | Owned temporary Pod probes for denied database/upstream paths; removes only its probe Pod. |
| `make external-client-verify` | Read-only natural-language prompts through a locally installed, signed-in Codex CLI plus SDK revocation check; creates/revokes a temporary member key and adds audit rows. |
| `make dashboard-live-verify` | Playwright admin/member flows, one-time key display, server status, and audit; creates/deactivates a test member and restores the demo upstream. |
| `make server-control-verify` | Authenticated disable/restore and owned Shipping pod/outage recovery; intentionally disrupts that demo upstream briefly and restores it. |

The [demo checklist](docs/demo-checklist.md) separates agent-run live checks, deterministic tests, and user-reported manual checkout. It records retained test products/orders and safe cleanup boundaries. Do not treat `make check` as evidence of a live deployment or a completed purchase.

## VPS/k3s deployment

The same chart renders with [`values-prod.yaml`](deploy/helm/bridgecart/values-prod.yaml), which is a **review template, not a deployed production configuration**. Replace every example hostname, image, Secret name, TLS Secret, and storage class. Point DNS for the shop, API, and dashboard hosts to the VPS/Traefik entrypoint; provide HTTPS certificates and `Secure` session cookies. Verify the target CNI enforces NetworkPolicies and Traefik supplies the Middleware/ServersTransport CRDs. Choose durable ReadWriteOnce storage and tested backups for MariaDB, PostgreSQL, and WordPress content. Provision production Secrets privately through an operator or secret manager; do not run local Secret generators or put values in Helm flags.

Build the five custom images from `frontend/`, `backend/`, and each independent `backend/services/*-mcp/` directory for the VPS node architecture, publish them to an accessible registry, and replace the `registry.example.com` image references with immutable reviewed tags or digests. For example, after a private `docker login`, set `REGISTRY`, `TAG`, and `TARGET_PLATFORM` for your registry and node, then run:

```sh
for component in frontend backend; do
  docker buildx build --platform "$TARGET_PLATFORM" --push \
    -t "$REGISTRY/bridgecart/$component:$TAG" "$component"
done
for service in woocommerce-mcp inventory-mcp shipping-mcp; do
  docker buildx build --platform "$TARGET_PLATFORM" --push \
    -t "$REGISTRY/bridgecart/$service:$TAG" "backend/services/$service"
done
```

Set all five corresponding image values to these published references. k3d uses `docker build` plus `k3d image import` through the Makefile; production nodes must instead be able to pull the published images. The pinned public WordPress, WP-CLI, MariaDB, and PostgreSQL images must also be pullable or preloaded. Before enabling backend on a fresh cluster, install the store and PostgreSQL first, then run the full upgrade so the Alembic migration Job can connect:

```sh
helm upgrade --install bridgecart deploy/helm/bridgecart -n bridgecart --create-namespace \
  -f deploy/helm/bridgecart/values-prod.yaml \
  --set backend.enabled=false --set backend.gateway.enabled=false \
  --set frontend.enabled=false --set woocommerceMcp.enabled=false \
  --set inventoryMcp.enabled=false --set shippingMcp.enabled=false --wait
helm upgrade --install bridgecart deploy/helm/bridgecart -n bridgecart \
  -f deploy/helm/bridgecart/values-prod.yaml --wait
```

These are **documented steps only**; this repository has not been verified on a VPS. Validate rendered charts and actual DNS, ingress/TLS, storage, Secret references, network paths, and backups on the target cluster before accepting traffic. See [production guidance](docs/production.md) and the [runbook](docs/runbook.md). Helm rollback restores manifests and image references, **not** Alembic, WooCommerce/plugin or MariaDB migrations, product/order writes, credentials, or audit changes. Back up data and the matching upstream Fernet key before upgrades. Plugin upgrades require an explicit reviewed version change and `allowPluginUpgrade` setting; downgrades are rejected by bootstrap.

## Limits and further detail

Local HTTP, three single-node `local-path` PVCs, one replica per database and backend, and an in-memory login limiter are suitable for a demo, not high availability. Inventory and shipping are deterministic examples, not integrations with stock or carriers. Chat requires a separately supplied Anthropic key and network access; it has bounded turns and browser-memory-only history. A gateway discovery cache can briefly show stale metadata, while execution checks server state again. Public HTTPS egress for Claude, admin-registered public MCP servers, and WordPress update checks cannot be narrowed to a hostname with ordinary Kubernetes NetworkPolicy. Retained PVCs survive Helm uninstall but **do not replace backups**.

**Stand-out work attempted:** [security hardening](docs/threat-model.md#gateway-and-upstream-trust) covers URL/redirect restrictions, encrypted upstream credentials, NetworkPolicies, and compatible non-root custom images; it does not implement per-tool permissions or OAuth. [Observability](docs/architecture.md#gateway-milestone-4b) includes safe upstream status reasons and user-attributed call audits, not metrics. [Upgrade and rollback guidance](docs/production.md) covers Helm and data limits; no VPS deployment or automatic database rollback is claimed. The optional multi-store provisioning bonus was not attempted.

Additional usability work includes safe Markdown replies with mobile-scrollable tables, visible audited tool traces, a reduced-motion-aware chat pending indicator, and a bounded Kubernetes WordPress scheduled-action runner. For operational detail, use [architecture](docs/architecture.md), [threat model](docs/threat-model.md), [local development](docs/local-development.md), [production](docs/production.md), [runbook](docs/runbook.md), and [verification history](docs/demo-checklist.md).
