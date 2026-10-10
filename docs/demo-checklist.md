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

## Existing local store activation — 2026-10-10

The existing `bridgecart` release was still at Helm revision 6 and had not received the local Live setting. WordPress reported `woocommerce_coming_soon=yes`, `show_on_front=posts`, and an assigned Shop page ID of 5. A logged-out Chrome session saw the Coming soon page at `/shop/`; demo product SKU `BRIDGECART-DEMO-001` and order #12 were present in the database.

- Added local-only `bootstrap.makeShopHomepage: true` and a one-time Shop homepage assignment. Production values keep both this and `makeStoreLive` false.
- `make store-deploy` upgraded the existing release to revision 7. The Job preserved WordPress and the demo product, set Shop as homepage, and made the store Live. No raw or base64-encoded Secret value matched the Job log.
- In a logged-out Chrome session, both `/` and `/shop/` displayed **BridgeCart Demo Mug** with an Add to cart button, without the Coming soon page. A guest used India free shipping and cash on delivery to place order **#15**.
- `make store-bootstrap` upgraded to revision 8. The Job preserved the existing admin and product and did not reapply the one-time homepage or visibility changes. WordPress still reported `woocommerce_coming_soon=no`, `page_on_front=5`, and `woocommerce_shop_page_id=5`; the SKU count was **1**, and orders #12 and #15 remained present.
- The existing Secret and both PVC identities were unchanged. `make store-smoke`, `make check`, local and production Helm lint/template, and PHP lint passed. No reinstall, Secret rotation, PVC replacement, or production deployment occurred.

## Milestone-three verification — 2026-10-10

- `make check` passed after the MCP implementation: frontend lint/type/format/build, backend tests (8), WooCommerce MCP tests (6), inventory/shipping scaffolds (1 each), local and production Helm lint/template. The MCP image `bridgecart/woocommerce-mcp:0.3.4` built and the existing release upgraded to revision **13**. WordPress, MariaDB, and MCP were Ready; original PVCs and store Secret remained in place.
- A temporary labeled in-cluster Pod initialized the official Python MCP SDK's Streamable HTTP client, listed exactly the five required tools, and called product/order tools. Missing and invalid bearer credentials returned HTTP 401. The internal Service was ClusterIP only.
- `create_product` created published **product #17**, “BridgeCart MCP Milestone Three Test Mug,” at ₹129. A logged-out headless Chrome session saw its public product page, added it to cart, and completed guest checkout with India free shipping and cash on delivery. The checkout confirmation created **order #18**. These are intentionally retained test artifacts.
- `list_orders(today=true)` returned #18 and prior same-day orders without customer address/contact fields. `get_order(18)` returned the test line item. `update_order_status(18, completed)` returned `completed`; a second `get_order` and WooCommerce admin both confirmed that status. Admin login with the existing Secret worked. No pre-existing order was modified.
- Network checks used positive controls: the labeled verification Pod reached MCP TCP 8001 and MCP reached WordPress TCP 80 (both `connect_ex=0`). An unlabeled Pod to MCP and MCP to MariaDB TCP 3306 were refused (`connect_ex=111`). Both manually created temporary Pods were ownership-checked and removed; the documented `make mcp-verify` then passed and removed its own temporary Pod.
- The first test image used OAuth query parameters, which placed only the consumer-key identifier in a WordPress access log. The consumer secret and MCP bearer did **not** appear. The corrected `0.3.4` image uses the `Authorization` header; its authenticated calls passed. The dedicated API key was rotated once and the prior logged identifier revoked. A subsequent Secret-aware log scan found neither current API key field in recent WordPress logs. This rotation did not touch the pre-existing store Secret or data.
- The local provisioner reran and reported `existing`, confirming it did not create another credential. The provisioner PHP passed `php -l` inside the WordPress pod; the host did not have PHP installed. The store bootstrap hook completed on chart upgrades without reinstalling WordPress or resetting products/orders. The test product and order remain for demonstrations; remove them only by an intentional store-admin action.
