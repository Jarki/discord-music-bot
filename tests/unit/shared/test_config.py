"""Unit tests for the configuration model."""

import os

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from src.shared.models.config import Settings


def test_discord_token_is_required(mocker: MockerFixture) -> None:
    """The bot cannot be configured without an authentication token."""
    mocker.patch.dict(os.environ, {}, clear=True)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert "discord_token" in str(exc_info.value)


def test_test_guild_id_rejects_non_string_values() -> None:
    """Guild IDs must use the string representation expected by Discord."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            discord_token="test-token",
            test_guild_id=12345,  # type: ignore[arg-type]
            _env_file=None,
        )

    assert "test_guild_id" in str(exc_info.value)


def test_constructor_values_take_precedence_over_environment(
    mocker: MockerFixture,
) -> None:
    """Explicit configuration wins over environment-provided values."""
    mocker.patch.dict(
        os.environ,
        {
            "DISCORD_TOKEN": "environment-token",
            "LOG_LEVEL": "WARNING",
        },
        clear=True,
    )

    settings = Settings(
        discord_token="constructor-token",
        log_level="DEBUG",
        _env_file=None,
    )

    assert settings.discord_token == "constructor-token"
    assert settings.log_level == "DEBUG"
