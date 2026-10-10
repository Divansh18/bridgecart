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

Before upgrades, back up MariaDB and WordPress content together and test restore. `make store-bootstrap` reruns the idempotent hook; it does not create a duplicate SKU. Changing the pinned WooCommerce version requires explicit `allowPluginUpgrade`, a backup, and compatibility review. Inspect revisions with `helm --kube-context k3d-bridgecart history bridgecart -n bridgecart`. To restore a prior workload manifest, use `helm --kube-context k3d-bridgecart rollback bridgecart <revision> -n bridgecart --wait`, then check pods, PVCs, product, and orders. `make store-deploy` returns to the current local values. Helm rollback does not reverse WooCommerce/WordPress database migrations. `helm uninstall` leaves both PVCs via resource-policy annotations; a completed hook Job may remain. Inspect and preserve them unless intentional data destruction is separately approved. Never delete an existing k3d cluster or PVC automatically.
