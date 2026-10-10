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
