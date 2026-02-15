.PHONY: install lint format test build docker clean status status-wallet status-cdp status-config status-faucet status-slack test-slack generate-wallet

# Wallet generation
TIDE_WALLET_KEY_FILE ?= ./tide-wallet.key

generate-wallet:
	@PYTHONPATH=src python3 -m tide --generate-wallet $(TIDE_WALLET_KEY_FILE)

# Development
install:
	pip install -r requirements-dev.txt

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

test:
	PYTHONPATH=src pytest tests/ -v --cov=tide --cov-report=term-missing

test-wallet:
	PYTHONPATH=src pytest tests/test_wallet.py -v

test-cdp:
	PYTHONPATH=src pytest tests/test_cdp.py tests/test_cdp_controller.py -v

test-client:
	PYTHONPATH=src pytest tests/test_client.py -v

test-faucet:
	PYTHONPATH=src pytest tests/test_rate_limiter.py tests/test_distributor.py tests/test_faucet_service.py -v

test-slack:
	PYTHONPATH=src pytest tests/test_slack_*.py -v

build: lint test

docker:
	docker build -t tide:local .

clean:
	rm -rf .pytest_cache .coverage .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Status targets - verify component functionality
status: status-config status-wallet status-cdp status-faucet status-slack
	@echo "All status checks completed"

status-config:
	@echo "=== Config Status ==="
	@PYTHONPATH=src python3 -c "\
from tide.config import TideConfig, CDPMode, CDPEmergencyAction; \
print('Config classes: OK'); \
print('  CDPMode values:', [m.value for m in CDPMode]); \
print('  CDPEmergencyAction values:', [a.value for a in CDPEmergencyAction]); \
"

status-wallet:
	@echo "=== Wallet Status ==="
	@PYTHONPATH=src python3 -c "\
from tide.core import WalletProvider, EnvironmentWallet; \
print('Wallet classes: OK'); \
print('  WalletProvider: abstract base class'); \
print('  EnvironmentWallet: loads from env or file'); \
"

status-cdp:
	@echo "=== CDP Status ==="
	@PYTHONPATH=src python3 -c "\
from tide.core import CDPManager, CDPController, CDPHealth, CDPStatus; \
print('CDP classes: OK'); \
print('  CDPHealth values:', [h.value for h in CDPHealth]); \
print('  CDPManager: core CDP operations'); \
print('  CDPController: mode-based CDP control'); \
"

status-blockchain:
	@echo "=== Blockchain Status ==="
	@PYTHONPATH=src python3 -c "\
from tide.blockchain import AutonityClient, NetworkInfo; \
print('Blockchain classes: OK'); \
print('  AutonityClient: ATN/NTN operations'); \
print('  NetworkInfo: network configuration'); \
"

status-faucet:
	@echo "=== Faucet Status ==="
	@PYTHONPATH=src python3 -c "\
from tide.faucet import RateLimiter, RateLimitResult; \
from tide.faucet import NTNDistributor, ATNDistributor, DistributionResult; \
from tide.faucet import FaucetService, FaucetResult, FaucetStatus; \
print('Faucet classes: OK'); \
print('  RateLimiter: per-user rate limiting'); \
print('  NTNDistributor: NTN token distribution'); \
print('  ATNDistributor: ATN via CDP borrowing'); \
print('  FaucetService: orchestrates all components'); \
"

status-slack:
	@echo "=== Slack Status ==="
	@PYTHONPATH=src python3 -c "\
from tide.slack import SlackAdapter, register_commands, MessageFormatter; \
print('Slack classes: OK'); \
print('  SlackAdapter: Socket Mode connection'); \
print('  register_commands: /tide command handlers'); \
print('  MessageFormatter: Block Kit responses'); \
"
