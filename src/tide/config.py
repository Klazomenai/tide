"""Configuration management for TIDE using Pydantic Settings."""

from enum import Enum

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class CDPMode(str, Enum):
    """CDP operation modes."""

    AUTO = "auto"
    MANUAL = "manual"
    DISABLED = "disabled"


class CDPEmergencyAction(str, Enum):
    """Emergency actions when CDP health is critical."""

    ALERT = "alert"
    REPAY = "repay"
    PAUSE = "pause"


class TideConfig(BaseSettings):
    """TIDE service configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Network
    rpc_endpoint: str = Field(alias="TIDE_RPC_ENDPOINT")
    chain_id: int | None = Field(default=None, alias="TIDE_CHAIN_ID")
    block_explorer_url: str | None = Field(default=None, alias="TIDE_BLOCK_EXPLORER_URL")

    # Wallet
    wallet_provider: str = Field(default="kubernetes", alias="TIDE_WALLET_PROVIDER")
    wallet_private_key: SecretStr | None = Field(default=None, alias="TIDE_WALLET_PRIVATE_KEY")
    wallet_private_key_file: str | None = Field(default=None, alias="TIDE_WALLET_PRIVATE_KEY_FILE")

    # Faucet limits
    max_atn: float = Field(default=5.0, alias="TIDE_MAX_ATN", gt=0)
    max_ntn: float = Field(default=50.0, alias="TIDE_MAX_NTN", gt=0)
    daily_limit: int = Field(default=10, alias="TIDE_DAILY_LIMIT", gt=0)
    cooldown_minutes: int = Field(default=60, alias="TIDE_COOLDOWN_MINUTES", gt=0)

    # CDP
    cdp_mode: CDPMode = Field(default=CDPMode.AUTO, alias="TIDE_CDP_MODE")
    cdp_auto_open: bool = Field(default=False, alias="TIDE_CDP_AUTO_OPEN")
    cdp_target_cr: float = Field(default=2.5, alias="TIDE_CDP_TARGET_CR")
    cdp_min_cr: float = Field(default=2.2, alias="TIDE_CDP_MIN_CR")
    cdp_max_cr: float = Field(default=3.0, alias="TIDE_CDP_MAX_CR")
    cdp_check_interval_minutes: int = Field(default=5, alias="TIDE_CDP_CHECK_INTERVAL_MINUTES")
    cdp_emergency_action: CDPEmergencyAction = Field(
        default=CDPEmergencyAction.ALERT, alias="TIDE_CDP_EMERGENCY_ACTION"
    )

    # Slack
    slack_bot_token: SecretStr | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    slack_app_token: SecretStr | None = Field(default=None, alias="SLACK_APP_TOKEN")
    slack_signing_secret: SecretStr | None = Field(default=None, alias="SLACK_SIGNING_SECRET")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")

    # Observability
    metrics_port: int = Field(default=8080, alias="TIDE_METRICS_PORT", ge=1, le=65535)
    log_level: str = Field(default="INFO", alias="TIDE_LOG_LEVEL")
    log_format: str = Field(default="json", alias="TIDE_LOG_FORMAT")
