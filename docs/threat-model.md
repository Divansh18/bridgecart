# Threat model: foundation

Sensitive assets will include WooCommerce credentials, API keys, audit records, and customer/store data. The current repository contains placeholders only. No service should receive an upstream secret through the frontend or a committed values file. MCP services are unauthenticated protocol shells in this milestone and must remain bound to loopback for local use; their Docker images are not safe to expose publicly.

Milestone two must define authenticated user identity, per-tool authorization, tenant isolation, credential storage and rotation, gateway-only access to upstream MCP, egress restrictions, audit integrity, request limits, transport security, and Kubernetes network policies before production use. Readiness is not a security check.
