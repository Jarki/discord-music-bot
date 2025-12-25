"""Global pytest fixtures for the loud_bot project.

This module provides fixtures that are available to all test modules.
"""

import time

import pytest

from src.shared.models.config import Settings


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Global fixture providing test configuration.

    This fixture creates a Settings instance with test-specific values.
    It overrides environment variables by passing values directly to the constructor.

    Scope: session - created once per test session for efficiency.

    Returns:
        Settings instance configured for testing
    """
    return Settings(
        # Override with test values (constructor args take precedence over .env)
        discord_token="test_token_12345",
        discord_command_prefix="!",
        sink_name="test_sink",
        audio_format="s16le",
        audio_rate=48000,
        audio_channels=2,
        api_host="127.0.0.1",
        api_port=8000,
        log_level="DEBUG",
    )


@pytest.fixture
def settings(test_settings: Settings) -> Settings:
    """Function-scoped fixture providing configuration to tests.

    Use this fixture in your tests to access configuration:

    Example:
        def test_example(settings):
            assert settings.discord_token == "test_token_12345"

    Args:
        test_settings: The session-scoped test settings fixture

    Returns:
        Settings instance configured for testing
    """
    return test_settings


@pytest.fixture
def timer():
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    print(f"\n⏱️  Test took {end - start:.4f} seconds")
