# TIDE

**Token Issuance for Developer Environments** — A Slack bot faucet for distributing ATN and NTN tokens on the [Autonity](https://autonity.org/) blockchain.

[![CI](https://github.com/klazomenai/tide/actions/workflows/ci.yml/badge.svg)](https://github.com/klazomenai/tide/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Features

- **Token Distribution** — Send ATN and NTN tokens via Slack slash commands
- **CDP Management** — Collateralized Debt Position management for sustainable ATN supply
- **Rate Limiting** — Redis-backed per-user daily limits and cooldowns
- **Observability** — Prometheus metrics, structured JSON logging, health/readiness endpoints
- **CLI Interface** — Full command-line interface for wallet, CDP, faucet, and governance operations
- **Kubernetes Ready** — Helm chart, health probes, configurable via environment variables

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  Slack API   │────▶│  TIDE Service │────▶│  Autonity RPC │
│  (Socket)    │◀────│              │◀────│               │
└─────────────┘     └──────┬───────┘     └───────────────┘
                           │
                    ┌──────┴───────┐
                    │    Redis     │
                    │ (Rate Limit) │
                    └──────────────┘
```

**Components:**

| Component | Purpose |
|-----------|---------|
| `slack/` | Slack adapter, command handlers, message formatting |
| `faucet/` | Token distribution, rate limiting, service orchestration |
| `core/` | Wallet management, CDP operations, CDP controller |
| `blockchain/` | Autonity client wrapper, network configuration |
| `observability/` | Prometheus metrics, health endpoints, structured logging |

## Quick Start

### Prerequisites

- Python 3.11+
- Redis (for rate limiting)
- An Autonity RPC endpoint
- Slack app credentials (for Slack integration)

### Install

```bash
# Clone the repository
git clone https://github.com/klazomenai/tide.git
cd tide

# Create virtual environment and install dependencies
make install
```

### Test

```bash
# Run tests with coverage
make test

# Run linting
make lint

# Format code
make format
```

### Run Locally

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your values

# Generate a wallet
python -m tide --generate-wallet ./tide-wallet.key

# CLI commands (no Slack needed)
PYTHONPATH=src python -m tide wallet address
PYTHONPATH=src python -m tide wallet balance

# Start the full service (requires Slack tokens)
PYTHONPATH=src python -m tide run
```

### CLI Commands

```
tide wallet address              Show wallet address
tide wallet balance              Show ATN and NTN balances
tide cdp status                  Show CDP status
tide cdp deposit <amount>        Deposit NTN collateral
tide cdp withdraw <amount>       Withdraw NTN collateral
tide cdp borrow <amount>         Borrow ATN against collateral
tide cdp repay <amount>          Repay ATN debt
tide faucet status               Show faucet balances
tide faucet atn <addr> [amount]  Send ATN to address
tide faucet ntn <addr> [amount]  Send NTN to address
tide governance cdp-status       Show CDP restriction status
tide governance get-supply-operator  Get ATN supply operator
tide governance set-supply-operator <addr>  Set ATN supply operator
```

Add `--json` for JSON output, `--dry-run` to preview without executing.

## Configuration

All configuration is via environment variables. See [`.env.example`](.env.example) for a complete template.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TIDE_RPC_ENDPOINT` | Yes | — | Autonity RPC endpoint URL |
| `TIDE_CHAIN_ID` | No | auto | Chain ID (auto-detected if not set) |
| `TIDE_BLOCK_EXPLORER_URL` | No | — | Block explorer base URL |
| `TIDE_WALLET_PROVIDER` | No | `kubernetes` | Wallet provider: `env`, `kubernetes`, `file` |
| `TIDE_WALLET_PRIVATE_KEY` | No | — | Hex private key (if provider=env) |
| `TIDE_WALLET_PRIVATE_KEY_FILE` | No | — | Path to key file (if provider=file) |
| `TIDE_MAX_ATN` | No | `5.0` | Maximum ATN per request |
| `TIDE_MAX_NTN` | No | `50.0` | Maximum NTN per request |
| `TIDE_DAILY_LIMIT` | No | `10` | Daily request limit per user |
| `TIDE_COOLDOWN_MINUTES` | No | `60` | Cooldown between requests (minutes) |
| `TIDE_CDP_MODE` | No | `auto` | CDP mode: `auto`, `manual`, `disabled` |
| `TIDE_CDP_AUTO_OPEN` | No | `false` | Auto-open CDP when needed |
| `TIDE_CDP_TARGET_CR` | No | `2.5` | Target collateralization ratio |
| `TIDE_CDP_MIN_CR` | No | `2.2` | Minimum CR before rebalancing |
| `TIDE_CDP_MAX_CR` | No | `3.0` | Maximum CR before rebalancing |
| `TIDE_CDP_CHECK_INTERVAL_MINUTES` | No | `5` | CDP health check interval |
| `TIDE_CDP_EMERGENCY_ACTION` | No | `alert` | Emergency action: `alert`, `repay`, `pause` |
| `SLACK_BOT_TOKEN` | Yes* | — | Slack bot token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes* | — | Slack app-level token (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | No | — | Slack signing secret |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection URL |
| `TIDE_METRICS_PORT` | No | `8080` | Prometheus metrics port |
| `TIDE_LOG_LEVEL` | No | `INFO` | Log level |
| `TIDE_LOG_FORMAT` | No | `json` | Log format: `json` or `text` |

*Required for Slack integration. CLI commands work without Slack tokens.

## Slack Commands

| Command | Description |
|---------|-------------|
| `/tide atn <address> [amount]` | Request ATN tokens (default: 1) |
| `/tide ntn <address> [amount]` | Request NTN tokens (default: 10) |
| `/tide status` | Show faucet status and balances |
| `/tide alerts` | Show active alerts |
| `/tide help` | Show help message |

## Docker

```bash
# Build
docker build -t tide:local .

# Run
docker run --env-file .env tide:local
```

## Helm Deployment

A Helm chart is included for Kubernetes deployment. See [`helm/README.md`](helm/README.md) for details.

```bash
cd helm
cp values-example.yaml values-local.yaml
# Edit values-local.yaml with your configuration
make install
```

## Project Structure

```
tide/
├── .github/workflows/ci.yml     # CI/CD pipeline
├── helm/                         # Helm chart for Kubernetes
├── src/tide/
│   ├── blockchain/               # Autonity client, network config
│   ├── core/                     # Wallet, CDP manager, controller
│   ├── faucet/                   # Distributor, rate limiter, service
│   ├── observability/            # Metrics, health, logging
│   ├── slack/                    # Adapter, commands, formatter
│   ├── cli.py                    # CLI interface
│   ├── config.py                 # Pydantic settings
│   └── main.py                   # Entry point
├── tests/                        # Test suite (249 tests)
├── Dockerfile
├── Makefile
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Run tests (`make test`) and linting (`make lint`)
4. Commit with conventional commits (`feat:`, `fix:`, `docs:`, etc.)
5. Open a pull request

## License

[MIT](LICENSE)
