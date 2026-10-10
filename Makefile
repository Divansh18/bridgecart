.PHONY: install frontend backend mcp-woocommerce mcp-inventory mcp-shipping lint typecheck format-check test build helm-check scripts-check check store-cluster store-secrets store-images store-deploy store-bootstrap store-status store-smoke store-admin-rotate mcp-secrets mcp-image mcp-deploy mcp-status mcp-verify backend-secrets backend-image backend-deploy backend-status backend-verify backend-live-verify

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

scripts-check:
	python3 -m py_compile scripts/provision_woocommerce_mcp.py scripts/rotate_woocommerce_mcp_key.py scripts/verify_mcp_cluster.py scripts/mcp_incluster_verify.py scripts/backend_secrets.py scripts/verify_backend_postgres.py scripts/verify_backend_live.py scripts/local_invite.py

check: lint typecheck format-check test build helm-check scripts-check

store-cluster:
	python3 scripts/cluster_setup.py

store-secrets:
	python3 scripts/store_secrets.py

store-images:
	sh scripts/prepare_store_images.sh

store-deploy:
	@mcp_enabled=$$(kubectl --context k3d-bridgecart -n bridgecart get secret bridgecart-woocommerce-api bridgecart-mcp-bearer >/dev/null 2>&1 && echo true || echo false); \
	backend_enabled=$$(kubectl --context k3d-bridgecart -n bridgecart get deployment bridgecart-backend >/dev/null 2>&1 && echo true || echo false); \
	postgres_enabled=$$(kubectl --context k3d-bridgecart -n bridgecart get statefulset bridgecart-postgres >/dev/null 2>&1 && echo true || echo false); \
	helm --kube-context k3d-bridgecart upgrade --install bridgecart deploy/helm/bridgecart --namespace bridgecart -f deploy/helm/bridgecart/values-local.yaml --set woocommerceMcp.enabled=$$mcp_enabled --set backend.enabled=$$backend_enabled --set postgres.enabled=$$postgres_enabled --wait --timeout 20m

store-bootstrap: store-deploy

store-status:
	kubectl --context k3d-bridgecart -n bridgecart get pods,pvc,svc,ingress,networkpolicy,job

store-smoke:
	python3 scripts/store_smoke.py

store-admin-rotate:
	python3 scripts/rotate_local_admin.py

mcp-secrets:
	python3 scripts/provision_woocommerce_mcp.py

mcp-image:
	docker build -t bridgecart/woocommerce-mcp:0.3.4 services/woocommerce-mcp
	k3d image import bridgecart/woocommerce-mcp:0.3.4 -c bridgecart

mcp-deploy: mcp-secrets mcp-image
	@backend_enabled=$$(kubectl --context k3d-bridgecart -n bridgecart get deployment bridgecart-backend >/dev/null 2>&1 && echo true || echo false); \
	postgres_enabled=$$(kubectl --context k3d-bridgecart -n bridgecart get statefulset bridgecart-postgres >/dev/null 2>&1 && echo true || echo false); \
	helm --kube-context k3d-bridgecart upgrade --install bridgecart deploy/helm/bridgecart --namespace bridgecart -f deploy/helm/bridgecart/values-local.yaml --set backend.enabled=$$backend_enabled --set postgres.enabled=$$postgres_enabled --wait --timeout 20m

mcp-status:
	kubectl --context k3d-bridgecart -n bridgecart get deployment/bridgecart-woocommerce-mcp service/bridgecart-woocommerce-mcp networkpolicy/bridgecart-woocommerce-mcp

mcp-verify:
	python3 scripts/verify_mcp_cluster.py

backend-secrets:
	python3 scripts/backend_secrets.py

backend-image:
	docker build -t bridgecart/backend:0.4.0 backend
	k3d image import bridgecart/backend:0.4.0 -c bridgecart

backend-deploy: backend-secrets backend-image
	@if ! kubectl --context k3d-bridgecart -n bridgecart get statefulset bridgecart-postgres >/dev/null 2>&1; then \
	  mcp_enabled=$$(kubectl --context k3d-bridgecart -n bridgecart get secret bridgecart-woocommerce-api bridgecart-mcp-bearer >/dev/null 2>&1 && echo true || echo false); \
	  helm --kube-context k3d-bridgecart upgrade --install bridgecart deploy/helm/bridgecart --namespace bridgecart -f deploy/helm/bridgecart/values-local.yaml --set backend.enabled=false --set postgres.enabled=true --set woocommerceMcp.enabled=$$mcp_enabled --wait --timeout 20m || exit $$?; \
	fi
	@mcp_enabled=$$(kubectl --context k3d-bridgecart -n bridgecart get secret bridgecart-woocommerce-api bridgecart-mcp-bearer >/dev/null 2>&1 && echo true || echo false); \
	helm --kube-context k3d-bridgecart upgrade --install bridgecart deploy/helm/bridgecart --namespace bridgecart -f deploy/helm/bridgecart/values-local.yaml --set woocommerceMcp.enabled=$$mcp_enabled --wait --timeout 20m
	kubectl --context k3d-bridgecart -n bridgecart rollout restart deployment/bridgecart-backend
	kubectl --context k3d-bridgecart -n bridgecart rollout status deployment/bridgecart-backend --timeout=5m

backend-status:
	kubectl --context k3d-bridgecart -n bridgecart get statefulset/bridgecart-postgres deployment/bridgecart-backend pvc/bridgecart-postgres-data ingress/bridgecart-api

backend-verify:
	python3 scripts/verify_backend_postgres.py

backend-live-verify:
	backend/.venv/bin/python scripts/verify_backend_live.py
