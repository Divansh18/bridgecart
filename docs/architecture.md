# Architecture

The store and milestone-three WooCommerce MCP service are isolated from the unfinished gateway. Traefik routes `shop.bridgecart.local:8088` to a single WordPress Apache pod. WordPress connects to an internal MariaDB Service. WordPress content and MariaDB data each use a separate ReadWriteOnce PVC. A post-install/post-upgrade WP-CLI Job mounts the WordPress PVC, runs as UID/GID 33 to match the Debian WordPress volume owner, and installs/configures WooCommerce. Both application containers keep their official image startup users so their entrypoints can prepare volume permissions; the chart uses RuntimeDefault seccomp and does not force an incompatible non-root UID.

The same Helm templates render for local k3d and production k3s. Local and production values set DNS, URL, storage class/size, TLS, Secret name, and demo behavior. Frontend, backend, inventory MCP, and shipping MCP workloads are disabled. WooCommerce MCP is an internal ClusterIP Service. The k3s Traefik, embedded network policy controller, and local-path provisioner are cluster facilities, not chart subcomponents.

WooCommerce starts a fresh store in Coming soon mode. Local demo values request a one-time Shop homepage assignment and a switch to Live at the end of bootstrap. Separate WordPress options record these initial changes so later bootstrap runs do not override an administrator's homepage or visibility choice. Production values request neither change.

NetworkPolicies default-deny ingress and egress for store pods and WooCommerce MCP, then allow Traefik to reach WordPress on TCP 80, and MCP to reach WordPress on TCP 80, WordPress and bootstrap to reach MariaDB on TCP 3306, and WordPress/bootstrap to reach CoreDNS on TCP/UDP 53. Bootstrap alone can reach public TCP 443 to download WooCommerce. MariaDB has no permitted egress and no public Service, NodePort, or Ingress. WooCommerce MCP accepts TCP 8001 only from future gateway pods and, in local values, a temporary pod bearing the verification label. MCP egress permits WordPress and CoreDNS, never MariaDB. Kubelet probes are node-originated. See the [runbook](runbook.md) for a live denied-connection check.

WordPress liveness reads a static core image and stays healthy during a temporary database outage. Readiness requests the dynamic login page, which depends on WordPress and MariaDB. MariaDB startup/readiness use its official `healthcheck.sh --connect --innodb_initialized`; liveness checks the local connection. The bootstrap Job has a 900-second deadline and one retry. Helm waits for it during deployment.

The future browser application must still speak only to the FastAPI backend. The future gateway will own upstream MCP connections, discovery, routing, authorization, and auditing. Future chat tool calls must enter the gateway under the authenticated user; upstream credentials must never reach the frontend. No such gateway flow is implemented in this milestone.

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
