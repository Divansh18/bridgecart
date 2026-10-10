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

The local-path volumes bind to a k3d node. Pod replacement on that node retains data; deleting the cluster or PVC can destroy it. Keep backups of both MariaDB and WordPress content for any data you care about. Helm uninstall retains the two PVC objects through `helm.sh/resource-policy: keep`; it does not retain the k3d cluster. Do not delete the cluster or PVCs as a routine cleanup step.

For foundation development, Node 22, Python 3.12, uv, and PostgreSQL are still required. Copy `.env.example` to `.env`, set `BRIDGECART_DATABASE_URL`, export it, then run `make install`, `make frontend`, and `make backend`. These services are not part of the store chart.
