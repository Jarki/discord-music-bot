"""Application configuration management using Pydantic Settings.

This module provides a type-safe configuration model that loads settings from
environment variables and .env files.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Configuration is loaded from:
    1. Environment variables (case-insensitive)
    2. .env file (if present)
    3. Constructor arguments (highest precedence)

    All fields have defaults except discord_token which is required.

    Example:
        >>> settings = Settings()  # Loads from .env
        >>> settings = Settings(discord_token="custom")  # Override

    Attributes:
        discord_token: Discord bot authentication token (required)
        discord_command_prefix: Prefix for bot commands
        test_guild_id: Optional Discord guild ID for testing
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Discord configuration
    discord_token: str
    discord_command_prefix: str = "!"
    test_guild_id: str | None = None

    # Logging
    log_level: str = "INFO"


settings = Settings()  # type: ignore
