.PHONY: install frontend backend mcp-woocommerce mcp-inventory mcp-shipping lint typecheck format-check test build helm-check check store-cluster store-secrets store-images store-deploy store-bootstrap store-status store-smoke store-admin-rotate

PYTHON_PROJECTS := backend services/woocommerce-mcp services/inventory-mcp services/shipping-mcp

install:
	cd frontend && npm ci
	@for project in $(PYTHON_PROJECTS); do (cd $$project && uv sync --locked) || exit $$?; done

frontend:
	cd frontend && npm run dev

backend:
	cd backend && uv run --locked uvicorn bridgecart.main:app --reload --host 127.0.0.1 --port 8000

mcp-woocommerce:
	cd services/woocommerce-mcp && uv run --locked python -m woocommerce_mcp.server

mcp-inventory:
	cd services/inventory-mcp && uv run --locked python -m inventory_mcp.server

mcp-shipping:
	cd services/shipping-mcp && uv run --locked python -m shipping_mcp.server

lint:
	cd frontend && npm run lint
	@for project in $(PYTHON_PROJECTS); do (cd $$project && uv run --locked ruff check .) || exit $$?; done

typecheck:
	cd frontend && npm run typecheck
	@for project in $(PYTHON_PROJECTS); do (cd $$project && uv run --locked mypy) || exit $$?; done

format-check:
	cd frontend && npm run format:check
	@for project in $(PYTHON_PROJECTS); do (cd $$project && uv run --locked ruff format --check .) || exit $$?; done

test:
	@for project in $(PYTHON_PROJECTS); do (cd $$project && uv run --locked pytest) || exit $$?; done

build:
	cd frontend && npm run build

helm-check:
	helm lint deploy/helm/bridgecart -f deploy/helm/bridgecart/values-local.yaml
	helm template bridgecart deploy/helm/bridgecart -f deploy/helm/bridgecart/values-local.yaml > /dev/null
	helm lint deploy/helm/bridgecart -f deploy/helm/bridgecart/values-prod.yaml
	helm template bridgecart deploy/helm/bridgecart -f deploy/helm/bridgecart/values-prod.yaml > /dev/null

check: lint typecheck format-check test build helm-check

store-cluster:
	python3 scripts/cluster_setup.py

store-secrets:
	python3 scripts/store_secrets.py

store-images:
	sh scripts/prepare_store_images.sh

store-deploy:
	helm --kube-context k3d-bridgecart upgrade --install bridgecart deploy/helm/bridgecart --namespace bridgecart -f deploy/helm/bridgecart/values-local.yaml --wait --timeout 20m

store-bootstrap: store-deploy

store-status:
	kubectl --context k3d-bridgecart -n bridgecart get pods,pvc,svc,ingress,networkpolicy,job

store-smoke:
	python3 scripts/store_smoke.py

store-admin-rotate:
	python3 scripts/rotate_local_admin.py
