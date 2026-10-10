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

For foundation development, Node 22, Python 3.12, uv, and PostgreSQL are still required. Copy `.env.example` to `.env`, set `BRIDGECART_DATABASE_URL`, export it, then run `make install`, `make frontend`, and `make backend`. These services are not part of the store chart.

## MCP service

After the store is ready, run:

```sh
make mcp-secrets  # repeatable; creates dedicated API and bearer Secrets, then binds API key to shop_manager
make mcp-image    # builds pinned 0.3.4 image and imports it to k3d
make mcp-deploy   # upgrades the existing release without resetting the store
make mcp-status
make mcp-verify   # temporary labeled in-cluster client; removes its own Pod after checks
```

`make mcp-deploy` also runs the first two steps. A fresh `make store-deploy` installs the store with MCP disabled until both MCP Secrets exist, so first bootstrap can complete. Subsequent store upgrades keep MCP enabled once those Secrets exist. The local provisioner is fixed to context `k3d-bridgecart` and namespace `bridgecart`. It reuses Secrets on repeat runs and only creates a dedicated `bridgecart-mcp` shop-manager account and `read_write` WooCommerce key when absent. It does not use the admin password. It passes key material to WordPress PHP on stdin, uses file-backed Kubernetes Secret creation, and prints only created/existing state. It never prints key, secret, or bearer values. For an intentional local API-key rotation, use `python3 scripts/rotate_woocommerce_mcp_key.py`; it leaves the WordPress admin credential and MCP bearer untouched. Do not put these values in Helm files or command arguments.

The internal MCP URL is `http://bridgecart-woocommerce-mcp:8001/mcp` inside the cluster; it has no public port. The public storefront stays [shop.bridgecart.local:8088](http://shop.bridgecart.local:8088/). The REST client reaches `http://bridgecart-wordpress` inside Kubernetes and signs against WordPress's configured public host as WooCommerce expects. The bearer token authenticates MCP transport callers, while the WooCommerce key authenticates REST calls from the service. Keep them distinct. For manual tool calls, use the temporary verification Pod and `scripts/mcp_incluster_verify.py`; it reads the bearer from a Secret environment variable without printing it. `make mcp-verify` checks MCP initialization, the five-tool catalog, a product listing, and missing/invalid bearer rejection. `python3 scripts/verify_mcp_cluster.py <order-id>` additionally checks today's order list and that specific order, then cleans up its Pod.

Test artifacts from the 2026-10-10 verification are product **#17**, “BridgeCart MCP Milestone Three Test Mug” (₹129), and guest cash-on-delivery order **#18**. They remain in the store intentionally; do not remove other products or orders while cleaning up verification Pods. The local test product is visible to guests at `/product/bridgecart-mcp-milestone-three-test-mug/`.
