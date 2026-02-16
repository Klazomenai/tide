"""Tests for TIDE configuration management."""

import pytest
from pydantic import ValidationError

from tide.config import CDPEmergencyAction, CDPMode, TideConfig


class TestTideConfigDefaults:
    """Test default configuration values."""

    def test_minimal_config(self, monkeypatch):
        """Config loads with only required fields."""
        monkeypatch.setenv("TIDE_RPC_ENDPOINT", "http://localhost:8545")
        config = TideConfig()

        assert config.rpc_endpoint == "http://localhost:8545"
        assert config.wallet_provider == "kubernetes"
        assert config.max_atn == 5.0
        assert config.max_ntn == 50.0
        assert config.daily_limit == 10
        assert config.cooldown_minutes == 60

    def test_cdp_defaults(self, monkeypatch):
        """CDP settings have correct defaults."""
        monkeypatch.setenv("TIDE_RPC_ENDPOINT", "http://localhost:8545")
        config = TideConfig()

        assert config.cdp_mode == CDPMode.AUTO
        assert config.cdp_auto_open is False
        assert config.cdp_target_cr == 2.5
        assert config.cdp_min_cr == 2.2
        assert config.cdp_max_cr == 3.0
        assert config.cdp_check_interval_minutes == 5
        assert config.cdp_emergency_action == CDPEmergencyAction.ALERT

    def test_observability_defaults(self, monkeypatch):
        """Observability settings have correct defaults."""
        monkeypatch.setenv("TIDE_RPC_ENDPOINT", "http://localhost:8545")
        config = TideConfig()

        assert config.metrics_port == 8080
        assert config.log_level == "INFO"
        assert config.log_format == "json"
        assert config.redis_url == "redis://localhost:6379"


class TestTideConfigEnvVars:
    """Test environment variable loading."""

    def test_all_env_vars(self, monkeypatch):
        """Config loads all environment variables correctly."""
        monkeypatch.setenv("TIDE_RPC_ENDPOINT", "http://rpc.example.com:8545")
        monkeypatch.setenv("TIDE_WALLET_PROVIDER", "vault")
        monkeypatch.setenv("TIDE_WALLET_PRIVATE_KEY", "0xdeadbeef")
        monkeypatch.setenv("TIDE_MAX_ATN", "10.5")
        monkeypatch.setenv("TIDE_MAX_NTN", "100.0")
        monkeypatch.setenv("TIDE_DAILY_LIMIT", "20")
        monkeypatch.setenv("TIDE_COOLDOWN_MINUTES", "30")
        monkeypatch.setenv("TIDE_CDP_MODE", "manual")
        monkeypatch.setenv("TIDE_CDP_EMERGENCY_ACTION", "repay")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("REDIS_URL", "redis://redis.example.com:6379")
        monkeypatch.setenv("TIDE_LOG_LEVEL", "DEBUG")

        config = TideConfig()

        assert config.rpc_endpoint == "http://rpc.example.com:8545"
        assert config.wallet_provider == "vault"
        assert config.wallet_private_key.get_secret_value() == "0xdeadbeef"
        assert config.max_atn == 10.5
        assert config.max_ntn == 100.0
        assert config.daily_limit == 20
        assert config.cooldown_minutes == 30
        assert config.cdp_mode == CDPMode.MANUAL
        assert config.cdp_emergency_action == CDPEmergencyAction.REPAY
        assert config.slack_bot_token.get_secret_value() == "xoxb-test"
        assert config.redis_url == "redis://redis.example.com:6379"
        assert config.log_level == "DEBUG"


class TestTideConfigValidation:
    """Test configuration validation."""

    def test_missing_required_field(self):
        """Missing required field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TideConfig()

        errors = exc_info.value.errors()
        assert len(errors) == 1
        # Pydantic uses alias in error location
        assert errors[0]["loc"] == ("TIDE_RPC_ENDPOINT",)
        assert errors[0]["type"] == "missing"

    def test_invalid_cdp_mode(self, monkeypatch):
        """Invalid CDP mode raises ValidationError."""
        monkeypatch.setenv("TIDE_RPC_ENDPOINT", "http://localhost:8545")
        monkeypatch.setenv("TIDE_CDP_MODE", "invalid_mode")

        with pytest.raises(ValidationError) as exc_info:
            TideConfig()

        errors = exc_info.value.errors()
        # Pydantic uses alias (TIDE_CDP_MODE) in error location
        assert any("TIDE_CDP_MODE" in str(e["loc"]) for e in errors)

    def test_invalid_emergency_action(self, monkeypatch):
        """Invalid emergency action raises ValidationError."""
        monkeypatch.setenv("TIDE_RPC_ENDPOINT", "http://localhost:8545")
        monkeypatch.setenv("TIDE_CDP_EMERGENCY_ACTION", "explode")

        with pytest.raises(ValidationError) as exc_info:
            TideConfig()

        errors = exc_info.value.errors()
        # Pydantic uses alias in error location
        assert any("TIDE_CDP_EMERGENCY_ACTION" in str(e["loc"]) for e in errors)

    def test_invalid_numeric_type(self, monkeypatch):
        """Invalid numeric type raises ValidationError."""
        monkeypatch.setenv("TIDE_RPC_ENDPOINT", "http://localhost:8545")
        monkeypatch.setenv("TIDE_MAX_ATN", "not_a_number")

        with pytest.raises(ValidationError) as exc_info:
            TideConfig()

        errors = exc_info.value.errors()
        # Pydantic uses alias in error location
        assert any("TIDE_MAX_ATN" in str(e["loc"]) for e in errors)


class TestCDPModeEnum:
    """Test CDPMode enum."""

    def test_all_modes(self):
        """All CDP modes are defined."""
        assert CDPMode.AUTO == "auto"
        assert CDPMode.MANUAL == "manual"
        assert CDPMode.DISABLED == "disabled"

    def test_mode_values(self):
        """CDP modes have string values."""
        assert CDPMode.AUTO.value == "auto"
        assert CDPMode.MANUAL.value == "manual"
        assert CDPMode.DISABLED.value == "disabled"


class TestCDPEmergencyActionEnum:
    """Test CDPEmergencyAction enum."""

    def test_all_actions(self):
        """All emergency actions are defined."""
        assert CDPEmergencyAction.ALERT == "alert"
        assert CDPEmergencyAction.REPAY == "repay"
        assert CDPEmergencyAction.PAUSE == "pause"
