# WooCommerce store demo checklist

- [ ] `make store-cluster` reuses or creates the cluster after port checks; Traefik is ready.
- [ ] `make store-secrets` creates or preserves the local Secret without outputting credentials.
- [ ] `make store-deploy` completes; `make store-status` shows both pods Ready, both PVCs Bound, and bootstrap Job Complete.
- [ ] `make store-smoke` checks storefront, product, cart, empty-cart checkout redirect, and login page.
- [ ] Browser: open `http://shop.bridgecart.local:8088/` and `/wp-admin/` (hosts entry required), using the generated admin password privately.
- [ ] Browser: add **BridgeCart Demo Mug** to cart, enter an India shipping address, select free shipping and cash on delivery, and place an order.
- [ ] Admin: confirm the new order and product SKU `BRIDGECART-DEMO-001` in WooCommerce.
- [ ] Replace WordPress and MariaDB pods as in the runbook; verify the product and order remain and PVCs stay Bound.
- [ ] Confirm an unlabeled diagnostic pod cannot connect to MariaDB while WordPress can.
- [ ] Run `make store-bootstrap` again; confirm the Job says the demo product already exists and there is still one matching SKU.
- [ ] `make check` passes Helm lint/template for local and production values plus the foundation checks.
- [ ] Review upgrade and rollback limits; do not claim database/plugin migrations are automatically reversible.

## Isolated fresh-install verification — 2026-10-10

An initial isolated `bridgecart-freshcheck` install completed, but a guest saw WooCommerce's default Coming soon page instead of the product. Bootstrap now sets the **local demo** store to Live after checkout and product setup, once per store; production values leave visibility unchanged. After correcting this, the final chart was installed from scratch as `bridgecart-finalcheck` in namespace `bridgecart-finalcheck-20261010`, using a separately generated Secret, empty MariaDB and WordPress PVCs, and `finalcheck.bridgecart.local:8088`.

- Fresh install: Helm revision 1 deployed; WordPress and MariaDB were 1/1 Ready, both 5 GiB PVCs Bound, and the bootstrap Job Complete. Its log confirmed a fresh WordPress install, WooCommerce 11.2.1 installation, Live visibility, and creation of `BRIDGECART-DEMO-001`.
- Browser: headless Chrome opened the distinct host using a temporary DNS override. The generated admin credential logged in successfully. A guest bought the demo mug with India free shipping and cash on delivery; order **#13** appeared on the confirmation page and in WooCommerce admin.
- Repeatability: Helm revision 2 reran bootstrap. The Job reported that it preserved the installed admin and existing product. The SKU count remained **1**, the order count remained **1**, and order #13 remained present.
- Credential check: both Job logs were compared in memory against the raw and base64-encoded values of all 11 Secret keys. Neither log contained an exact match; no Secret values were printed during the check.
- Cleanup: every resource in each verification namespace was checked against its temporary release or namespace before uninstall. Both namespaces, their Secrets, test PVCs and backing PVs, and Ingresses were removed. The original `bridgecart` release remained deployed at revision 6; its Secret and PVC identities were unchanged, and its demo product and order #12 remained present.
- Project checks: `make check` passed, including local and production Helm lint/template. PHP lint passed for both bootstrap PHP files.
