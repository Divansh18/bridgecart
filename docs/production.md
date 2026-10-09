# Production plan

Production is intended for k3s. The chart is a configuration scaffold and produces no Kubernetes resources in this milestone. Do not run `helm install` expecting an application. The `values-prod.yaml` host is a placeholder, not a database provisioner.

Milestone two must add Deployments, Services, probes, migrations, ingress/TLS, external PostgreSQL wiring, secret references, workload identities, network policy, persistent storage decisions, and an authenticated gateway before production deployment. Pin and publish reviewed images and inject secrets through a secret manager rather than values files.
