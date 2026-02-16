# TIDE Helm Chart

TIDE (Token Issuance for Developer Environments) - Slack bot faucet for Autonity testnets.

## Prerequisites

- Kubernetes cluster
- Helm 3.x
- Redis (see `manifests/redis.yaml`)
- Image pull secret for GHCR (`ghcr-pull-secret`)

## Quick Start

```bash
# Setup namespace, Redis, and secrets
make setup

# Deploy TIDE
make deploy
```

## Configuration

### Required

| Value | Description |
|-------|-------------|
| `config.rpcEndpoint` | Autonity RPC endpoint |
| `secrets.existingSecret` | K8s secret with Slack tokens and wallet key |

### Secret Keys

The secret must contain:

| Key | Description |
|-----|-------------|
| `SLACK_BOT_TOKEN` | Slack bot token (xoxb-...) |
| `SLACK_APP_TOKEN` | Slack app-level token (xapp-...) |
| `SLACK_SIGNING_SECRET` | Slack signing secret |
| `TIDE_WALLET_PRIVATE_KEY` | Wallet private key for faucet transactions |

### Values Files

- `values.yaml` - Default configuration
- `values-example.yaml` - Example deployment configuration

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Create namespace, Redis, and secrets |
| `make deploy` | Deploy TIDE via Helm |
| `make status` | Show deployment status |
| `make logs` | Tail TIDE logs |
| `make teardown` | Remove all TIDE resources |

## Redis

Ephemeral Redis is provided via `manifests/redis.yaml`. For production deployments, add persistent storage.
