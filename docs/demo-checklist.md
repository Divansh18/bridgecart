# Foundation demo checklist

- [ ] Open the landing screen at `http://localhost:5173`.
- [ ] Show `/health/live` returning 200.
- [ ] Show `/health/ready` returning 200 with PostgreSQL available and 503 when unavailable.
- [ ] Connect an MCP client to each service and show an empty tool list.
- [ ] Run `make check` and review the lockfiles.
- [ ] Show that Helm lint/template validates the scaffold and emits no workload manifests.
