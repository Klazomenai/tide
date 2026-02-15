"""Pytest configuration and fixtures for TIDE tests."""

import os

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clear TIDE-related environment variables before each test."""
    env_prefixes = ("TIDE_", "SLACK_", "REDIS_")
    for key in list(os.environ.keys()):
        if key.startswith(env_prefixes):
            monkeypatch.delenv(key, raising=False)
