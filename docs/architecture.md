# Architecture

The store, WooCommerce MCP service, and team API are isolated from the unfinished gateway. Traefik routes `shop.bridgecart.local:8088` to a single WordPress Apache pod. WordPress connects to an internal MariaDB Service. WordPress content and MariaDB data each use a separate ReadWriteOnce PVC. A post-install/post-upgrade WP-CLI Job mounts the WordPress PVC, runs as UID/GID 33 to match the Debian WordPress volume owner, and installs/configures WooCommerce. Both application containers keep their official image startup users so their entrypoints can prepare volume permissions; the chart uses RuntimeDefault seccomp and does not force an incompatible non-root UID.

The same Helm templates render for local k3d and production k3s. Local and production values set DNS, URL, storage class/size, TLS, Secret name, and demo behavior. Frontend, inventory MCP, and shipping MCP workloads are disabled. WooCommerce MCP is an internal ClusterIP Service. The k3s Traefik, embedded network policy controller, and local-path provisioner are cluster facilities, not chart subcomponents.

WooCommerce starts a fresh store in Coming soon mode. Local demo values request a one-time Shop homepage assignment and a switch to Live at the end of bootstrap. Separate WordPress options record these initial changes so later bootstrap runs do not override an administrator's homepage or visibility choice. Production values request neither change.

NetworkPolicies default-deny ingress and egress for store pods and WooCommerce MCP, then allow Traefik to reach WordPress on TCP 80, and MCP to reach WordPress on TCP 80, WordPress and bootstrap to reach MariaDB on TCP 3306, and WordPress/bootstrap to reach CoreDNS on TCP/UDP 53. Bootstrap alone can reach public TCP 443 to download WooCommerce. MariaDB has no permitted egress and no public Service, NodePort, or Ingress. WooCommerce MCP accepts TCP 8001 only from future gateway pods and, in local values, a temporary pod bearing the verification label. MCP egress permits WordPress and CoreDNS, never MariaDB. Kubelet probes are node-originated. See the [runbook](runbook.md) for a live denied-connection check.

WordPress liveness reads a static core image and stays healthy during a temporary database outage. Readiness requests the dynamic login page, which depends on WordPress and MariaDB. MariaDB startup/readiness use its official `healthcheck.sh --connect --innodb_initialized`; liveness checks the local connection. The bootstrap Job has a 900-second deadline and one retry. Helm waits for it during deployment.

The future browser application must speak only to the FastAPI backend. The future gateway will own upstream MCP connections, discovery, routing, authorization, and auditing. Future chat tool calls must enter the gateway under the authenticated user; upstream credentials must never reach the frontend. No such gateway flow is implemented in this milestone.

## WooCommerce MCP tools

The internal MCP endpoint is `http://bridgecart-woocommerce-mcp:8001/mcp` using Streamable HTTP. Its bearer token comes from `bridgecart-mcp-bearer`; this authenticates transport clients but is not team authorization. The WooCommerce REST API key comes from `bridgecart-woocommerce-api`, belongs to a dedicated `shop_manager` WordPress account, and is used only inside the MCP service. These credentials have different purposes and must be rotated separately. Tool read/write annotations describe side effects but do not enforce authorization. Future gateway authorization must precede every tool call.

| Tool | Arguments | Result |
| --- | --- | --- |
| `list_products` | `page` 1–1000, `per_page` 1–50, optional `search` up to 200 characters | Product IDs, names, status, prices, public permalinks, pagination total |
| `create_product` | Name 1–200 characters, non-negative decimal-string `price` with at most two fractional digits | New product ID and public URL |
| `list_orders` | Bounded page/per_page, optional supported `status`, `today`, `after`, `before` ISO dates | Order IDs, status, total, currency, date, and line items; no billing, shipping, email, or phone |
| `get_order` | Positive `order_id` | Same restricted order projection |
| `update_order_status` | Positive `order_id`, status in `pending`, `processing`, `on-hold`, `completed`, `cancelled`, `refunded`, `failed` | ID and resulting status |

`today=true` means midnight to the next midnight in `Asia/Kolkata`; the client converts those boundaries to UTC and sets `dates_are_gmt=true`. It cannot be combined with `after` or `before`. ISO date filters refer to whole calendar days in the store's configured timezone (currently Asia/Kolkata). The REST API's strict date boundaries are widened by one second on the lower side.

The service calls the [WooCommerce REST v3 API](https://developer.woocommerce.com/docs/apis/rest-api/) because it supports authenticated product creation and order management; WooCommerce's public Store API is intended for storefront interactions. Over internal HTTP, the client signs OAuth 1.0a with HMAC-SHA256 and sends it in `Authorization`. WooCommerce verifies using the WordPress public host and the internal request's HTTP scheme; those addresses are configured separately. The WordPress Apache `.htaccess` forwards `Authorization` to PHP. For an internal HTTPS API, the client uses Basic authentication as documented by [WooCommerce authentication](https://developer.woocommerce.com/docs/apis/rest-api/authentication/). The public URL is returned only as a product permalink, never used as the network target.

A shared async HTTPX client has bounded pool and request timeouts and closes at shutdown. Reads and writes are not retried automatically. A write timeout or connection failure is reported as an uncertain outcome; inspect WooCommerce before retrying to avoid duplicate products or repeated order transitions. Health liveness checks only this process, while readiness makes a bounded authenticated products API request. Tool errors omit raw WooCommerce response bodies and credentials.

## Team access (milestone 4A)

Traefik routes `api.bridgecart.local:8088` to the FastAPI backend; its Service is ClusterIP. PostgreSQL is internal, single-replica, and uses a retained ReadWriteOnce PVC separate from MariaDB and WordPress content. The backend and a pre-upgrade migration Job are the only allowed PostgreSQL clients. A first local deployment creates PostgreSQL while backend is disabled, then the next Helm upgrade runs Alembic and idempotent initial-admin provisioning before the backend becomes Ready. Readiness checks the current Alembic revision and database; liveness checks the process only. The backend image runs as UID/GID 10001 on a read-only root filesystem; the official PostgreSQL entrypoint retains its compatible startup user for volume ownership.

The API has four persisted tables: `users`, `login_sessions`, `invitations`, and `api_keys`. Passwords use salted scrypt (`N=32768`, `r=8`, `p=1`). Session, CSRF, invitation, and API-key tokens are generated with `secrets` and stored only as domain-separated SHA-256 hashes. Session cookies are HttpOnly; a separate readable CSRF cookie must match `X-CSRF-Token` and the session's stored CSRF hash for cookie-authenticated mutations. Local HTTP uses `Secure=false`, `SameSite=Lax`; production requires `Secure=true`. API keys are a distinct `Bearer bck_…` credential type, checked against revocation and user activity on every use by `authenticate_api_key`; no public probe endpoint exposes that component.

The initial admin comes only from a Kubernetes Secret. Admins invite members by email and receive a single-use, expiring token once; delivery is a private operator workflow, not email. Members can manage only their own API keys. Admins can list/deactivate members and issue/list/revoke member keys. The raw API key appears only in its creation response. Routes validate input and return safe errors without echoing submitted secrets. Login has a bounded in-process failure limiter; its counters are single-replica and reset on restart. Gateway aggregation, authorization of MCP tool calls, routing, and audit logs remain milestone 4B.

| API | Access | Behavior |
| --- | --- | --- |
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | Session | Login sets opaque session and CSRF cookies; logout requires CSRF and revokes the session. |
| `POST /invitations`, `POST /auth/invitations/accept` | Admin session / single-use token | Create a member invitation; accept it with a new password. |
| `GET /members`, `POST /members/{id}/deactivate` | Admin session | List members and deactivate members. |
| `GET/POST /api-keys`, `DELETE /api-keys/{id}` | Member's session | List own metadata, create a key, or revoke own key. |
| `GET/POST /members/{id}/api-keys`, `DELETE /members/{id}/api-keys/{key_id}` | Admin session | Manage a member's keys. |

All cookie-authenticated POST/DELETE mutations other than login and invitation acceptance require the matching CSRF cookie and header. API-key authentication is internal reusable code for milestone 4B; API keys are not accepted on these session routes.
