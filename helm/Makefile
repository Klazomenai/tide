.PHONY: lint template deploy status logs uninstall \
        setup teardown \
        create-namespace create-secret create-redis \
        delete-namespace delete-secret delete-redis

NAMESPACE ?= tide
RELEASE_NAME ?= tide
VALUES_FILE ?= values-example.yaml
SECRET_NAME ?= tide-credentials

# --- Helm Operations ---

lint:
	helm lint .

template:
	helm template $(RELEASE_NAME) . -n $(NAMESPACE) -f $(VALUES_FILE)

deploy:
	helm upgrade --install $(RELEASE_NAME) . \
		-n $(NAMESPACE) \
		-f $(VALUES_FILE)

status:
	@echo "=== Namespace ==="
	@kubectl get ns $(NAMESPACE) 2>/dev/null || echo "Namespace $(NAMESPACE) not found"
	@echo ""
	@echo "=== Pods ==="
	@kubectl get pods -n $(NAMESPACE) 2>/dev/null || echo "No pods found"
	@echo ""
	@echo "=== Secrets ==="
	@kubectl get secrets -n $(NAMESPACE) $(SECRET_NAME) 2>/dev/null || echo "Secret $(SECRET_NAME) not found"
	@echo ""
	@echo "=== Services ==="
	@kubectl get svc -n $(NAMESPACE) 2>/dev/null || echo "No services found"

logs:
	kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/name=tide -f

uninstall:
	helm uninstall $(RELEASE_NAME) -n $(NAMESPACE)

# --- Setup/Teardown (ArgoCD-friendly) ---

setup: create-namespace create-redis create-secret
	@echo "Setup complete. Run 'make deploy' to install TIDE."

teardown: uninstall delete-redis delete-secret delete-namespace
	@echo "Teardown complete."

# --- Namespace ---

create-namespace:
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl label namespace $(NAMESPACE) app.kubernetes.io/name=tide --overwrite

delete-namespace:
	kubectl delete namespace $(NAMESPACE) --ignore-not-found

# --- Secrets ---
# Create secret interactively - prompts for values
# For CI/CD, use: kubectl create secret generic ... --from-literal=...

create-secret:
	@echo "Creating secret $(SECRET_NAME) in namespace $(NAMESPACE)"
	@echo "You will be prompted for each value (leave empty to skip):"
	@echo ""
	@read -s -p "SLACK_BOT_TOKEN (xoxb-...): " SLACK_BOT_TOKEN && echo "" && \
	read -s -p "SLACK_APP_TOKEN (xapp-...): " SLACK_APP_TOKEN && echo "" && \
	read -s -p "SLACK_SIGNING_SECRET: " SLACK_SIGNING_SECRET && echo "" && \
	read -s -p "TIDE_WALLET_PRIVATE_KEY (0x...): " TIDE_WALLET_PRIVATE_KEY && echo "" && \
	kubectl create secret generic $(SECRET_NAME) \
		-n $(NAMESPACE) \
		--from-literal=SLACK_BOT_TOKEN="$$SLACK_BOT_TOKEN" \
		--from-literal=SLACK_APP_TOKEN="$$SLACK_APP_TOKEN" \
		--from-literal=SLACK_SIGNING_SECRET="$$SLACK_SIGNING_SECRET" \
		--from-literal=TIDE_WALLET_PRIVATE_KEY="$$TIDE_WALLET_PRIVATE_KEY" \
		--dry-run=client -o yaml | kubectl apply -f -

delete-secret:
	kubectl delete secret $(SECRET_NAME) -n $(NAMESPACE) --ignore-not-found

# --- Redis ---

create-redis:
	kubectl apply -n $(NAMESPACE) -f manifests/redis.yaml

delete-redis:
	kubectl delete -n $(NAMESPACE) -f manifests/redis.yaml --ignore-not-found

# --- Helpers ---

check-redis:
	kubectl exec -n $(NAMESPACE) -it deploy/redis -- redis-cli ping

describe:
	kubectl describe pods -n $(NAMESPACE) -l app.kubernetes.io/name=tide
