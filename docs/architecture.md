# Architecture

The milestone-two store is isolated from the unfinished gateway. Traefik routes `shop.bridgecart.local:8088` to a single WordPress Apache pod. WordPress connects to an internal MariaDB Service. WordPress content and MariaDB data each use a separate ReadWriteOnce PVC. A post-install/post-upgrade WP-CLI Job mounts the WordPress PVC, runs as UID/GID 33 to match the Debian WordPress volume owner, and installs/configures WooCommerce. Both application containers keep their official image startup users so their entrypoints can prepare volume permissions; the chart uses RuntimeDefault seccomp and does not force an incompatible non-root UID.

The same Helm templates render for local k3d and production k3s. Local and production values set DNS, URL, storage class/size, TLS, Secret name, and demo behavior. Frontend, backend, and MCP workloads are explicitly disabled. The k3s Traefik, embedded network policy controller, and local-path provisioner are cluster facilities, not chart subcomponents.

WooCommerce starts a fresh store in Coming soon mode. Local demo values request a one-time Shop homepage assignment and a switch to Live at the end of bootstrap. Separate WordPress options record these initial changes so later bootstrap runs do not override an administrator's homepage or visibility choice. Production values request neither change.

NetworkPolicies default-deny ingress and egress for store pods, then allow Traefik to reach WordPress on TCP 80, WordPress and bootstrap to reach MariaDB on TCP 3306, and WordPress/bootstrap to reach CoreDNS on TCP/UDP 53. Bootstrap alone can reach public TCP 443 to download WooCommerce. MariaDB has no permitted egress and no public Service, NodePort, or Ingress. Kubelet probes are node-originated. See the [runbook](runbook.md) for a live denied-connection check.

WordPress liveness reads a static core image and stays healthy during a temporary database outage. Readiness requests the dynamic login page, which depends on WordPress and MariaDB. MariaDB startup/readiness use its official `healthcheck.sh --connect --innodb_initialized`; liveness checks the local connection. The bootstrap Job has a 900-second deadline and one retry. Helm waits for it during deployment.

The future browser application must still speak only to the FastAPI backend. The future gateway will own upstream MCP connections, discovery, routing, authorization, and auditing. Future chat tool calls must enter the gateway under the authenticated user; upstream credentials must never reach the frontend. No such flow is implemented in this milestone.
