# Store runbook

All local commands target `--context k3d-bridgecart` and namespace `bridgecart`; do not rely on the current kubectl context. Start with `make store-status`, `make store-smoke`, and `helm --kube-context k3d-bridgecart status bridgecart -n bridgecart`. For bootstrap failure, inspect the Job status, pod events, and Job logs. Never paste Secret values into logs or tickets.

## Health and data

WordPress startup/liveness use a static file. WordPress readiness uses `/wp-login.php`; if it fails, inspect WordPress logs and MariaDB readiness. MariaDB probes use `healthcheck.sh`. PVCs must be `Bound`. Inspect `kubectl --context k3d-bridgecart -n bridgecart get pods,pvc,events` and check volume ownership if a Job cannot write WordPress files. The official Apache image prepares the volume as UID/GID 33; the WP-CLI Job explicitly runs as 33:33 because its Alpine default differs.

To replace pods without deleting PVCs:

```sh
kubectl --context k3d-bridgecart -n bridgecart delete pod -l app.kubernetes.io/component=wordpress
kubectl --context k3d-bridgecart -n bridgecart rollout status deployment/bridgecart-wordpress --timeout=10m
kubectl --context k3d-bridgecart -n bridgecart delete pod bridgecart-mariadb-0
kubectl --context k3d-bridgecart -n bridgecart rollout status statefulset/bridgecart-mariadb --timeout=10m
```

The WordPress Deployment uses Recreate to avoid a simultaneous writer on its RWO volume. The MariaDB StatefulSet keeps one stable pod identity. Verify the same product/order after replacement. This does not test node loss or backup recovery.

## Network checks

The database has only ClusterIP Services; there is no public route. From a WordPress pod, a PHP mysqli connection using its injected environment should succeed. An unlabeled diagnostic pod in the store namespace should time out connecting to `bridgecart-mariadb:3306`, while resolving the Service DNS name. Delete only that diagnostic pod afterward. This is the enforcement check; the presence of NetworkPolicy resources alone is insufficient.

Allowed paths are host `127.0.0.1:8088` → k3d load balancer → Traefik → WordPress TCP 80; WordPress/Bootstrap → MariaDB TCP 3306; WordPress/Bootstrap → CoreDNS TCP/UDP 53; Bootstrap → public HTTPS TCP 443 for the pinned plugin. MariaDB has no permitted egress. Kubelet probe traffic originates from nodes and is not a public store path.

## Upgrade, uninstall, recovery

Before upgrades, back up MariaDB and WordPress content together and test restore. `make store-bootstrap` reruns the idempotent hook; it does not create a duplicate SKU. Changing the pinned WooCommerce version requires explicit `allowPluginUpgrade`, a backup, and compatibility review. Inspect revisions with `helm --kube-context k3d-bridgecart history bridgecart -n bridgecart`. To restore a prior workload manifest, use `helm --kube-context k3d-bridgecart rollback bridgecart <revision> -n bridgecart --wait`, then check pods, PVCs, product, and orders. `make store-deploy` returns to the current local values. Helm rollback does not reverse WooCommerce/WordPress database migrations. `helm uninstall` leaves the store PVCs and, when enabled, the PostgreSQL PVC via resource-policy annotations; a completed hook Job may remain. Inspect and preserve them unless intentional data destruction is separately approved. Never delete an existing k3d cluster or PVC automatically.

## MCP incidents and verification

Run `make mcp-status` and `make mcp-verify`. MCP `/health/live` checks process liveness; `/health/ready` performs one bounded authenticated WooCommerce REST read and returns 503 when WordPress, its database, or the API credential is unavailable. A liveness success with readiness failure should direct investigation to WordPress/API credentials, not trigger a restart loop. Inspect `kubectl --context k3d-bridgecart -n bridgecart logs deploy/bridgecart-woocommerce-mcp` without sharing raw logs. The service suppresses HTTP access logs and never logs Authorization headers or REST bodies.

A write timeout is ambiguous: look up the product by name or order by ID in WooCommerce before retrying. The MCP client never retries writes automatically. For local WooCommerce key rotation, run `python3 scripts/rotate_woocommerce_mcp_key.py`. It creates a replacement key, updates only the dedicated API Secret, restarts the MCP Deployment, waits for readiness, then revokes the old key. Rotate the MCP bearer separately and update authorized gateway clients. `make mcp-secrets` preserves existing values and does not rotate. The API key is distinct from the WordPress admin password.

Network controls: the only allowed MCP ingress is from future gateway-labeled pods, plus local temporary Pods with `bridgecart.dev/mcp-verify=true`. MCP egress reaches WordPress TCP 80 and CoreDNS TCP/UDP 53; it cannot reach MariaDB TCP 3306. The milestone-three verification used positive controls (labeled client → MCP and MCP → WordPress both connected) and negative controls (unlabeled client → MCP and MCP → MariaDB returned connection refusal). Check actual connections because a rendered NetworkPolicy alone does not prove enforcement. Remove temporary Pods after verifying their `bridgecart.dev/temporary-owner=milestone-three` label.

## Team API

Run `make backend-status` and check `http://api.bridgecart.local:8088/health/live` and `/health/ready` with the API host mapped to loopback. Liveness is database-independent; readiness checks PostgreSQL and Alembic revision `20261010_01`. Inspect the failed `bridgecart-backend-migrate` Job and pod events if readiness stays 503 after an upgrade. The migration Job is a pre-upgrade Helm hook, so the first PostgreSQL-only phase is required on fresh releases. Do not print Secret data while diagnosing. Rerunning `make backend-deploy` preserves existing admin credentials, users, sessions, invitations, API keys, and the PostgreSQL PVC.

`make backend-verify` creates and drops only its own random test database. `make backend-live-verify` is a deliberate live check: it creates or reuses the `milestone4a-member@bridgecart.local` account, `bridgecart-demo-member` Secret, and two named keys; it replaces only the backend pod after checking its ownership label. These are retained test artifacts. The test scans logs for the credential values it used but does not print them. For a manual network check, an unlabeled pod should fail to reach `bridgecart-postgres:5432`, while `/health/ready` should remain 200 as the positive backend control. Verify actual connections, not only rendered policies.

The PostgreSQL claim is marked `helm.sh/resource-policy: keep` on uninstall; inspect it before any intentional removal. Its local-path volume may be lost with the k3d node or cluster. Back up PostgreSQL separately from MariaDB and WordPress content. Before a backend upgrade, test the migration and backup restore. Roll back manifests only with a compatible schema; Alembic and application writes are not automatically reversible. If a user is deactivated or an API key revoked, the next authenticated request is denied because the verifier checks PostgreSQL every time. Session and API-key credentials have distinct stores and cannot be interchanged.
