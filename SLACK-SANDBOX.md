# TIDE Slack App Setup in Developer Sandbox

Step-by-step guide to create and configure a TIDE Slack app in a Developer Sandbox for testing.

## Prerequisites

- Slack Developer Program account
- Developer Sandbox provisioned
- TIDE service code (this repository)

## Step 1: Provision Developer Sandbox

1. Go to [Sandboxes](https://api.slack.com/developer-program/sandboxes)
2. Click **Provision Sandbox**
3. Choose **Empty sandbox** (1 workspace, 1 demo user)
4. Click **Provision Sandbox** again
5. Access sandbox via the email login link

## Step 2: Create Slack App via Manifest

1. Go to [Your Apps](https://api.slack.com/apps)
2. Click **Create New App** → **From an app manifest**
3. Select your **sandbox workspace**
4. Paste this YAML manifest:

```yaml
display_information:
  name: TIDE Faucet
  description: Token Issuance for Developer Environments - Autonity testnet faucet
  background_color: "#2c2d30"

features:
  bot_user:
    display_name: TIDE
    always_online: true
  slash_commands:
    - command: /tide
      description: Request tokens from the Autonity faucet
      usage_hint: "[atn|ntn|status|alerts|help] [address] [amount]"
      should_escape: false

oauth_config:
  scopes:
    bot:
      - commands
      - chat:write
      - chat:write.public

settings:
  socket_mode_enabled: true
  org_deploy_enabled: false
  is_hosted: false
  token_rotation_enabled: false
```

5. Click **Next** → **Create**

## Step 3: Enable Socket Mode & Get App Token

1. In app settings, go to **Socket Mode** (left sidebar)
2. Toggle **Enable Socket Mode** → ON
3. When prompted, create an app-level token:
   - Name: `tide-socket`
   - Scope: `connections:write`
4. Click **Generate**
5. Copy the **App Token** (starts with `xapp-`)

## Step 4: Install App to Workspace

1. Go to **OAuth & Permissions** (left sidebar)
2. Click **Install to Workspace**
3. Authorize the requested permissions
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

## Step 5: Get Signing Secret (Optional)

1. Go to **Basic Information** (left sidebar)
2. Under **App Credentials**, find **Signing Secret**
3. Click **Show** and copy (used for request verification)

## Step 6: Configure TIDE Environment

Set these environment variables for TIDE:

```bash
# Required for Socket Mode
export SLACK_BOT_TOKEN="xoxb-..."      # From Step 4
export SLACK_APP_TOKEN="xapp-..."      # From Step 3

# Optional (for HTTP mode, not needed for Socket Mode)
export SLACK_SIGNING_SECRET="..."      # From Step 5
```

## Step 7: Test Locally

```bash
# Create virtual environment and install
make install

# Generate a test wallet
python -m tide --generate-wallet ./tide-wallet.key

# Configure environment
export TIDE_RPC_ENDPOINT="https://rpc.example.autonity.org/"
export TIDE_WALLET_PRIVATE_KEY_FILE="./tide-wallet.key"

# Test CLI commands first (no Slack needed)
PYTHONPATH=src python -m tide wallet address
PYTHONPATH=src python -m tide wallet balance

# Start TIDE service with Slack
PYTHONPATH=src python -m tide run
```

## Step 8: Test in Slack

In your sandbox workspace:

1. Type `/tide help` - Should show help message
2. Type `/tide status` - Should show faucet status
3. Type `/tide atn 0x...address... 1` - Request 1 ATN

## Token Reference

| Token | Prefix | Purpose | Where to Find |
|-------|--------|---------|---------------|
| Bot Token | `xoxb-` | API calls | OAuth & Permissions |
| App Token | `xapp-` | Socket Mode connection | Socket Mode settings |
| Signing Secret | (none) | Request verification | Basic Information |

## Troubleshooting

### "not_authed" error
- Verify `SLACK_BOT_TOKEN` is correct and starts with `xoxb-`

### Socket connection fails
- Verify `SLACK_APP_TOKEN` is correct and starts with `xapp-`
- Ensure Socket Mode is enabled in app settings

### Command not found
- Reinstall app to workspace after manifest changes
- Verify `/tide` command is defined in Features → Slash Commands

## Sources

- [Developer Sandboxes](https://docs.slack.dev/tools/developer-sandboxes/)
- [App Manifest Reference](https://docs.slack.dev/reference/app-manifest/)
- [Using Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)
- [Socket Mode Client (Python)](https://docs.slack.dev/tools/python-slack-sdk/socket-mode/)
