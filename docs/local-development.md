# Local development

## Requirements and host mapping

Use Docker Desktop, k3d 5.9+, kubectl, Helm 4 (or compatible Helm 3), Python 3.12+, and enough free disk for two 5 GiB PVC requests and images. `deploy/k3d/cluster.yaml` pins k3s `v1.35.2-k3s1`. It maps host `127.0.0.1:8088` to Traefik port 80, and Kubernetes API port `127.0.0.1:6550`. K3s includes Traefik, its network policy controller, and local-path storage by default. Do not disable network policy in this cluster.

Add this hosts entry once, after checking for an existing mapping:

```text
127.0.0.1 shop.bridgecart.local
```

On macOS/Linux, edit `/etc/hosts` with your normal administrator workflow. `make store-smoke` sends the Host header directly to loopback and does not need this entry. The storefront URL is `http://shop.bridgecart.local:8088/`; admin is `/wp-admin/`. The chart stores that exact public URL in WordPress to keep cart and checkout redirects on the local host.

## Fresh checkout

```sh
make store-cluster   # reuses an existing bridgecart cluster; checks 6550 and 8088 before creation
make store-secrets   # creates namespace and a generated local Secret, or preserves an existing one
make store-deploy    # Helm install/upgrade with a bounded bootstrap Job
make store-status
make store-smoke
```

Use `make store-images` before deployment only if k3d nodes cannot pull the pinned public images. This imports the same image tags listed in `values.yaml`. The bootstrap Job still needs HTTPS access to download the pinned WooCommerce plugin from WordPress.org on first install. If it fails, inspect `kubectl --context k3d-bridgecart -n bridgecart describe job bridgecart-store-bootstrap` and its pod events; the Job is bounded by 900 seconds and Helm reports failure.

The local Secret is `bridgecart/bridgecart-store-credentials`. It contains database passwords, stable WordPress authentication salts, and the admin password. The bootstrap script uses the admin password from a mounted file inside PHP; it is never placed in command arguments or Job output. If the Secret already exists, the script checks required keys and leaves all values untouched. To retrieve the admin password privately for a browser login, run this on your own terminal and keep the output out of shared logs:

```sh
kubectl --context k3d-bridgecart -n bridgecart get secret bridgecart-store-credentials -o jsonpath='{.data.wordpress-admin-password}' | base64 --decode
```

The username is `bridgecart-admin`. `make store-admin-rotate` rotates its local password in both WordPress and the Secret without printing it. Production Secret creation is separate.

## Repeatability and limits

`make store-bootstrap` repeats the Helm upgrade and bootstrap hook. It preserves an installed admin and checks the demo product by SKU before creating one. It does not delete products or orders. The hook updates the configured public URL, timezone, permalinks, currency, and enabled demo checkout settings. WooCommerce is pinned to 11.2.1. An already installed different version causes a clear failure unless `allowPluginUpgrade` is explicitly enabled for a reviewed forward upgrade.

WooCommerce starts a fresh store in Coming soon mode. Local values set `bootstrap.makeStoreLive: true` and `bootstrap.makeShopHomepage: true`, so BridgeCart makes the demo store Live and sets the assigned WooCommerce Shop page as the WordPress homepage during bootstrap. Separate markers prevent later bootstrap runs from overriding visibility or homepage changes made by an administrator. Production values leave both settings false; publish a production store only after reviewing its configuration and using WooCommerce > Settings > Site visibility. See [WooCommerce's site visibility documentation](https://woocommerce.com/document/configuring-woocommerce-settings/coming-soon-mode/) and [Shop page documentation](https://woocommerce.com/document/woocommerce-pages/).

The local-path volumes bind to a k3d node. Pod replacement on that node retains data; deleting the cluster or PVC can destroy it. Keep backups of both MariaDB and WordPress content for any data you care about. Helm uninstall retains the two PVC objects through `helm.sh/resource-policy: keep`; it does not retain the k3d cluster. Do not delete the cluster or PVCs as a routine cleanup step.

For foundation development, Node 22, Python 3.12, uv, and PostgreSQL are still required. Copy `.env.example` to `.env`, set `BRIDGECART_DATABASE_URL`, export it, then run `make install`, `make frontend`, and `make backend`. Use `make dashboard-deploy` to deploy the dashboard and updated backend through the same chart.

## MCP service

After the store is ready, run:

```sh
make mcp-secrets  # repeatable; creates dedicated API and bearer Secrets, then binds API key to shop_manager
make mcp-image    # builds pinned 0.3.4 image and imports it to k3d
make mcp-deploy   # upgrades the existing release without resetting the store
make mcp-status
```

`make mcp-deploy` also runs the first two steps. A fresh `make store-deploy` installs the store with MCP disabled until both MCP Secrets exist, so first bootstrap can complete. Subsequent store upgrades keep MCP enabled once those Secrets exist. The local provisioner is fixed to context `k3d-bridgecart` and namespace `bridgecart`. It reuses Secrets on repeat runs and only creates a dedicated `bridgecart-mcp` shop-manager account and `read_write` WooCommerce key when absent. It does not use the admin password. It passes key material to WordPress PHP on stdin, uses file-backed Kubernetes Secret creation, and prints only created/existing state. It never prints key, secret, or bearer values. For an intentional local API-key rotation, use `python3 scripts/rotate_woocommerce_mcp_key.py`; it leaves the WordPress admin credential and MCP bearer untouched. Do not put these values in Helm files or command arguments.

The internal MCP URL is `http://bridgecart-woocommerce-mcp:8001/mcp` inside the cluster; it has no public port. The public storefront stays [shop.bridgecart.local:8088](http://shop.bridgecart.local:8088/). The REST client reaches `http://bridgecart-wordpress` inside Kubernetes and signs against WordPress's configured public host as WooCommerce expects. The bearer token authenticates MCP transport callers, while the WooCommerce key authenticates REST calls from the service. Keep them distinct. Use the external gateway at `http://api.bridgecart.local:8088/mcp` with a user API key. `make mcp-verify` runs the current gateway smoke check, including all three upstreams; the milestone-three temporary upstream access label and Pod helper have been removed.

Test artifacts from the 2026-10-10 verification are product **#17**, “BridgeCart MCP Milestone Three Test Mug” (₹129), and guest cash-on-delivery order **#18**. They remain in the store intentionally; do not remove other products or orders while cleaning up verification Pods. The local test product is visible to guests at `/product/bridgecart-mcp-milestone-three-test-mug/`.

## Team API (milestone 4A)

After the store and MCP are running, install the locked backend development environment (`cd backend && uv sync --locked`) for the verification helpers, then run:

```sh
make gateway-deploy  # backend-deploy is an alias in the current repository
make backend-status
make backend-verify
make backend-live-verify
```

`make gateway-deploy` creates or preserves the team API's two local Secrets: `bridgecart-postgres-credentials` (`password`, `database-url`) and `bridgecart-initial-admin` (`admin-email`, `admin-password`). It generates values with the OS CSPRNG, writes temporary files with mode 0600 for `kubectl create secret`, and prints only created/existing state. The backend admin email is `admin@bridgecart.local`; its generated password is distinct from WordPress admin and never appears in Helm values. An existing admin is preserved on migration reruns; bootstrap never resets its password. To retrieve it for a private login, use your own terminal and do not paste the output into shared logs:

```sh
kubectl --context k3d-bridgecart -n bridgecart get secret bridgecart-initial-admin -o jsonpath='{.data.admin-password}' | base64 --decode
```

The API host is `api.bridgecart.local` on the same loopback port 8088 as the shop. Add `127.0.0.1 api.bridgecart.local` to `/etc/hosts` for browser/API-client use. The API docs are at `http://api.bridgecart.local:8088/docs`; the dashboard is at `http://app.bridgecart.local:8088/`. Local HTTP uses an HttpOnly `bridgecart_session` cookie with `SameSite=Lax`, plus a readable `bridgecart_csrf` cookie. Send the CSRF cookie's value in `X-CSRF-Token` for all authenticated POST/PATCH/DELETE requests. Login and invitation acceptance do not require a session. `GET /auth/me` checks current session activity; `POST /auth/logout` revokes it. API keys are separate Bearer credentials for the gateway and cannot replace session cookies on these routes.

For a private invitation handoff, run the following with the locked backend environment. The first command logs in using the local admin Secret internally and writes the single-use token to a new 0600 file without printing it. Give that file to the invited member through an appropriate private channel. The second command prompts for their new password without echoing it. Remove the used token file intentionally afterward:

```sh
backend/.venv/bin/python scripts/local_invite.py create member@example.com /private/tmp/bridgecart-member-invite
backend/.venv/bin/python scripts/local_invite.py accept /private/tmp/bridgecart-member-invite
rm /private/tmp/bridgecart-member-invite
```

An invitation expires after 72 hours and can be accepted once. There is no public signup or email delivery. Admins create invitations with `POST /invitations`, list members with `GET /members`, and deactivate members with `POST /members/{id}/deactivate`. A member uses `GET/POST /api-keys` and `DELETE /api-keys/{id}` for their own keys; admins use the corresponding `/members/{id}/api-keys` routes. API-key creation returns the raw `bck_…` key **once**. Lists return only ID, owner, name, prefix, and timestamps. Store the creation response privately; the service cannot recover a raw key later. A revoked key or inactive user fails the next API-key authentication check. The gateway uses the reusable verifier on each transport request and tool execution; it has no public debug endpoint.

`make backend-verify` port-forwards PostgreSQL only for the test process, creates a random temporary database, runs Alembic, exercises admin/member/session/invitation/key boundaries, and drops only that test database. `make backend-live-verify` uses the API Ingress, creates or reuses a clearly named demo member and a separate `bridgecart-demo-member` Secret for its generated password, checks admin/member keys, replaces only the backend pod, and checks the same records again. It leaves the demo member and keys in PostgreSQL; it does not touch WooCommerce products or orders. Run it intentionally, not as part of `make check`.

PostgreSQL uses one local-path RWO PVC and one pod. Its claim has Helm's `keep` policy, but the volume is tied to the k3d node. Backend session and key data survive pod replacement; neither the PVC nor the single-replica database provides a backup or high availability. Login rate limiting is in memory (five login attempts per client/email in five minutes, resetting after success), so a restart resets counters and multiple backend replicas would not share them. Use a shared limiter and trusted client-IP handling before horizontal scaling. Local HTTP is for loopback demos; production requires TLS and Secure cookies.

## Gateway (milestone 4B)

From a fresh checkout, first follow the store and WooCommerce MCP steps above, then install the locked Python dependencies and deploy the gateway:

```sh
make install
make gateway-deploy
make gateway-status
make backend-verify
make backend-live-verify  # supplies the existing named local demo member for the live gateway check
make gateway-verify
make gateway-outage-verify
make gateway-network-verify
```

`make gateway-secrets`, included in deployment, creates or preserves `bridgecart-upstream-encryption` (`fernet-key`), `bridgecart-inventory-mcp-bearer` (`token`), and `bridgecart-shipping-mcp-bearer` (`token`). The WooCommerce bearer remains in its existing separate Secret. The local script uses CSPRNG values and private temporary files, never sends secret material in a shell argument, and prints only created/existing state. Rerunning it does **not** rotate anything. The gateway encryption key must be backed up with PostgreSQL; losing it makes persisted upstream credentials undecryptable. Rotate it only through a coordinated re-encryption procedure, which is not automated here. Do not use this local script for production.

The migration Job runs Alembic and seeds the three upstream registrations only if their deterministic IDs have never existed. Disabling, editing, or soft removing one is preserved on the next deploy. Admin session routes `GET/POST /servers`, `PATCH/DELETE /servers/{id}` manage the allowlisted Streamable HTTP endpoints. `GET /servers` includes safe status, diagnostic category, and tool schemas; it never returns stored bearer or custom-header values. Registry mutations require the same CSRF cookie/header as other admin mutations. `GET /audit?page=1&per_page=20` is paginated; members see only their own rows, admins may filter `user_id`. Add another approved destination to `backend.gateway.allowedUrls` and a matching `backend.gateway.extraEgress` component/port entry before an admin registers it. The target Pod must carry this release's selector labels plus that component label; verify its NetworkPolicy separately. The first three values are reserved for the seeded WooCommerce, inventory, and shipping registrations.

Use a user's one-time `bck_…` API key as `Authorization: Bearer …` at `http://api.bridgecart.local:8088/mcp`. The **public** gateway URL is distinct from internal `http://bridgecart-woocommerce-mcp:8001/mcp`, `http://bridgecart-inventory-mcp:8002/mcp`, and `http://bridgecart-shipping-mcp:8003/mcp`. Only the gateway receives a user key. It decrypts and sends each upstream's separate bearer; WooCommerce itself uses its separate REST API key for WordPress. A Streamable HTTP client must explicitly refresh `tools/list` after registry changes because this stateless gateway has no persistent tool-list push channel. The same open client can still attempt a cached name; the gateway checks enabled state again and rejects it. Revoking a user key rejects the next request on that connection.

The inventory and shipping tools use static demo data detailed in [architecture](architecture.md#gateway-milestone-4b). They do not change checkout totals, reserve stock, call carriers, or read the store/platform databases. `make gateway-verify` creates two short-lived user API keys, calls all three upstreams through the external gateway, checks audit attribution and credential-free logs, and revokes those keys in a `finally` block. It does not create products or orders. `make gateway-outage-verify` checks the shipping Deployment's ownership and one-replica state, scales it to zero, proves WooCommerce/inventory still work and status becomes `Unreachable`, then restores one replica and checks `Connected`. `make gateway-network-verify` creates one ownership-labeled temporary Pod, checks denied direct upstream access and demo-service database egress, then deletes only that Pod after comparing its UID. These checks require a working local cluster and are not part of `make check`.

## Dashboard (milestone five)

Add `127.0.0.1 app.bridgecart.local api.bridgecart.local` to `/etc/hosts` if missing. With the existing k3d cluster and team API running, run `make dashboard-deploy`, `make dashboard-status`, and `make dashboard-smoke`. Open `http://app.bridgecart.local:8088/`. The dashboard uses `/api` on that same origin; Traefik strips the prefix and forwards to FastAPI. The existing `http://api.bridgecart.local:8088/mcp` remains the external Streamable HTTP gateway. `frontend.gatewayUrl` controls the Connect screen at runtime. `make dashboard-deploy` disables the store bootstrap hook for this UI-only Helm upgrade; it does not modify WordPress, product, order, or PVC data. Later store-specific upgrades can run the idempotent bootstrap deliberately.

For development, run `make backend` and `make frontend`. Vite proxies `/api` to `127.0.0.1:8000` and removes the prefix. The local `frontend/public/config.js` shows the local gateway URL; production mounts a values-driven ConfigMap at the same path. Sign in with the BridgeCart team admin from the existing initial-admin Secret, not the WordPress admin. See the team access section above for private credential retrieval. Invitation links are shown once in Members; copy them privately and accept them at `/accept-invitation`. Members can create their own gateway API keys; admins can select a member and issue or revoke theirs. Raw keys appear only in the creation response and in the dashboard until dismissed or navigation. The dashboard never stores them in localStorage, sessionStorage, or URLs.

Admin registry changes require a destination already approved in `backend.gateway.allowedUrls` and permitted by NetworkPolicy. The editor leaves an existing credential untouched when **Keep** is selected, replaces it only when a new value is provided, or removes it when authentication is set to **None**. The backend does not return stored credentials. Members see a safe read-only catalog with tools and status. Audit supports backend pagination and an admin user filter; the backend currently has no server/outcome/time filters.

`make dashboard-live-verify` runs the Playwright browser acceptance helper when Python Playwright and its Chromium browser are installed. It reads the existing initial-admin Secret in memory, creates one uniquely named test member and one key, verifies the UI, revokes the key, deactivates the member, and writes screenshots under `/private/tmp/bridgecart-dashboard-screenshots`. It restores Demo Inventory after the controlled disable test. Do not run it against production; it is intentionally mutating. The helper maps the `.local` hostnames inside Chromium, so `/etc/hosts` changes are unnecessary for automated verification. Earlier interrupted helper runs may leave named test artifacts; the helper checks its own prefix and revokes/deactivates those on the next run.
