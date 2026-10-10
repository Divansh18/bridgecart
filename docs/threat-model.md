# Threat model

The current local store has a public HTTP ingress on loopback port 8088 for development. It has no TLS, and its demo checkout uses cash on delivery. Do not use it for real customers or payment information. WordPress admin and database credentials reside in a pre-created Kubernetes Secret. The local secret generator uses temporary 0600 files and never prints values; the Secret is not committed. Kubernetes operators with Secret read permission can still retrieve them.

NetworkPolicies reduce pod-to-pod reachability: only the labeled WordPress and bootstrap pods may connect to MariaDB, and only Traefik may reach WordPress through its pod network. The bootstrap pod has public HTTPS egress for a version-pinned plugin download. Host access, node-originated traffic, and privileged Kubernetes actors remain outside these pod policies. Verify enforcement on each target k3s cluster rather than treating YAML presence as proof.

Local-path PVCs preserve data across pod replacement on the same node but provide no cross-node redundancy or backup. Production requires TLS, durable storage, backup and restore exercises, secret management, and a review of WordPress/WooCommerce updates. The gateway and its user authorization are milestone-three work.
