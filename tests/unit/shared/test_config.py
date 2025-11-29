"""Unit tests for the configuration model."""

import os

import pytest
from pydantic import ValidationError

from src.shared.models.config import Settings


class TestSettingsDefaults:
    """Test default values in Settings."""

    def test_settings_default_values(self) -> None:
        """Test that Settings loads with default values when discord_token is provided."""
        settings = Settings(discord_token="test_token")

        assert settings.sink_name == "discord_capture"
        assert settings.audio_format == "s16le"
        assert settings.audio_rate == 48000
        assert settings.audio_channels == 2
        assert settings.discord_command_prefix == "!"
        assert settings.api_host == "127.0.0.1"
        assert settings.api_port == 8000
        assert settings.log_level == "INFO"

    def test_settings_discord_token_required(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that discord_token is required (no default value)."""
        # Clear environment variable to ensure it's not set
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]

        # Verify the error is about missing discord_token
        assert "discord_token" in str(exc_info.value)


class TestSettingsOverrides:
    """Test overriding default values."""

    def test_settings_override_defaults(self) -> None:
        """Test that constructor arguments override default values."""
        settings = Settings(
            discord_token="custom_token",
            sink_name="custom_sink",
            audio_rate=44100,
            api_port=9000,
        )

        assert settings.discord_token == "custom_token"
        assert settings.sink_name == "custom_sink"
        assert settings.audio_rate == 44100
        assert settings.api_port == 9000
        # Non-overridden values still use defaults
        assert settings.audio_channels == 2
        assert settings.log_level == "INFO"

    def test_settings_override_all_fields(self) -> None:
        """Test overriding all configuration fields."""
        settings = Settings(
            discord_token="token123",
            discord_command_prefix="?",
            sink_name="my_sink",
            audio_format="s32le",
            audio_rate=96000,
            audio_channels=1,
            api_host="0.0.0.0",
            api_port=3000,
            log_level="ERROR",
        )

        assert settings.discord_token == "token123"
        assert settings.discord_command_prefix == "?"
        assert settings.sink_name == "my_sink"
        assert settings.audio_format == "s32le"
        assert settings.audio_rate == 96000
        assert settings.audio_channels == 1
        assert settings.api_host == "0.0.0.0"
        assert settings.api_port == 3000
        assert settings.log_level == "ERROR"


class TestSettingsValidation:
    """Test Pydantic type validation."""

    def test_settings_type_validation(self) -> None:
        """Test that Pydantic validates types correctly."""
        # Valid types
        settings = Settings(discord_token="token", audio_rate=48000)
        assert isinstance(settings.audio_rate, int)
        assert isinstance(settings.discord_token, str)

    def test_settings_invalid_type_audio_rate(self) -> None:
        """Test that invalid audio_rate type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(discord_token="token", audio_rate="not_an_integer")  # type: ignore

        assert "audio_rate" in str(exc_info.value)

    def test_settings_invalid_type_api_port(self) -> None:
        """Test that invalid api_port type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(discord_token="token", api_port="invalid")  # type: ignore

        assert "api_port" in str(exc_info.value)

    def test_settings_type_coercion(self) -> None:
        """Test that Pydantic can coerce compatible types."""
        # String numbers can be coerced to int
        settings = Settings(discord_token="token", audio_rate="48000", api_port="8000")  # type: ignore

        assert settings.audio_rate == 48000
        assert settings.api_port == 8000
        assert isinstance(settings.audio_rate, int)
        assert isinstance(settings.api_port, int)


class TestSettingsCaseInsensitivity:
    """Test case-insensitive environment variable loading."""

    def test_settings_case_insensitive(self) -> None:
        """Test that env var names are case-insensitive."""
        # Temporarily set uppercase env var
        os.environ["DISCORD_TOKEN"] = "env_token"
        os.environ["SINK_NAME"] = "env_sink"

        try:
            settings = Settings()  # type: ignore[call-arg]
            assert settings.discord_token == "env_token"
            assert settings.sink_name == "env_sink"
        finally:
            # Cleanup
            os.environ.pop("DISCORD_TOKEN", None)
            os.environ.pop("SINK_NAME", None)

    def test_settings_lowercase_env_vars(self) -> None:
        """Test that lowercase env vars work due to case_sensitive=False."""
        os.environ["DISCORD_TOKEN"] = "lower_token"
        os.environ["API_PORT"] = "9999"

        try:
            settings = Settings()  # type: ignore[call-arg]
            assert settings.discord_token == "lower_token"
            assert settings.api_port == 9999
        finally:
            os.environ.pop("DISCORD_TOKEN", None)
            os.environ.pop("API_PORT", None)


class TestSettingsFixtures:
    """Test pytest fixtures."""

    def test_fixture_provides_test_settings(self, settings: Settings) -> None:
        """Test that the global settings fixture works correctly."""
        assert settings.discord_token == "test_token_12345"
        assert settings.sink_name == "test_sink"
        assert settings.log_level == "DEBUG"
        assert settings.audio_rate == 48000

    def test_fixture_provides_complete_config(self, settings: Settings) -> None:
        """Test that fixture provides all required configuration."""
        # All fields should be accessible
        assert settings.discord_token
        assert settings.discord_command_prefix
        assert settings.sink_name
        assert settings.audio_format
        assert settings.audio_rate > 0
        assert settings.audio_channels > 0
        assert settings.api_host
        assert settings.api_port > 0
        assert settings.log_level


class TestSettingsMutability:
    """Test Settings mutability (Pydantic v2 behavior)."""

    def test_settings_fields_mutable(self) -> None:
        """Test that Settings fields can be modified (Pydantic v2 allows this by default)."""
        settings = Settings(discord_token="token")

        # Pydantic v2 models are mutable by default
        settings.sink_name = "new_sink"
        assert settings.sink_name == "new_sink"

        settings.audio_rate = 96000
        assert settings.audio_rate == 96000

    def test_settings_mutability_preserves_other_fields(self) -> None:
        """Test that modifying one field doesn't affect others."""
        settings = Settings(discord_token="original_token")
        original_token = settings.discord_token

        settings.sink_name = "modified_sink"

        # Other fields remain unchanged
        assert settings.discord_token == original_token
        assert settings.audio_rate == 48000


class TestSettingsExtraFields:
    """Test handling of extra fields (extra='ignore' in config)."""

    def test_settings_ignores_extra_env_vars(self) -> None:
        """Test that extra environment variables are ignored."""
        os.environ["DISCORD_TOKEN"] = "test_token"
        os.environ["RANDOM_VAR"] = "should_be_ignored"
        os.environ["ANOTHER_EXTRA"] = "also_ignored"

        try:
            # Should not raise an error
            settings = Settings()  # type: ignore[call-arg]
            assert settings.discord_token == "test_token"

            # Extra fields should not be present
            assert not hasattr(settings, "random_var")
            assert not hasattr(settings, "another_extra")
        finally:
            os.environ.pop("DISCORD_TOKEN", None)
            os.environ.pop("RANDOM_VAR", None)
            os.environ.pop("ANOTHER_EXTRA", None)
