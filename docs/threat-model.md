# Threat model

The current local store has a public HTTP ingress on loopback port 8088 for development. It has no TLS, and its demo checkout uses cash on delivery. Do not use it for real customers or payment information. WordPress admin and database credentials reside in a pre-created Kubernetes Secret. The local secret generator uses temporary 0600 files and never prints values; the Secret is not committed. Kubernetes operators with Secret read permission can still retrieve them.

NetworkPolicies reduce pod-to-pod reachability: only the labeled WordPress and bootstrap pods may connect to MariaDB, and Traefik and WooCommerce MCP may reach WordPress through its pod network. The bootstrap pod has public HTTPS egress for a version-pinned plugin download. Host access, node-originated traffic, and privileged Kubernetes actors remain outside these pod policies. Verify enforcement on each target k3s cluster rather than treating YAML presence as proof.

Local-path PVCs preserve data across pod replacement on the same node but provide no cross-node redundancy or backup. Production requires TLS, durable storage, backup and restore exercises, secret management, and a review of WordPress/WooCommerce updates. The gateway and team authorization remain milestone-four work.

## Milestone-three MCP boundary

The WooCommerce API key and MCP bearer token are separate Kubernetes Secrets. The dedicated shop-manager key can read/write store resources and is held only by the MCP service. The bearer protects every Streamable HTTP transport request but does not identify a team member or authorize individual tool calls. The future gateway must authenticate users, authorize tool use, and audit each call before reaching MCP. Tools expose reduced order fields to avoid unnecessary customer contact data. NetworkPolicies block direct MCP-to-MariaDB traffic and public MCP access, but correctness depends on a policy-enforcing CNI and Secret RBAC. OAuth on internal HTTP is placed in `Authorization`, avoiding query-string credential logging; future production deployments should prefer TLS for sensitive east-west traffic where supported.
