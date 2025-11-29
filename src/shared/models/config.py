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
        sink_name: Name of the PulseAudio/PipeWire null sink
        audio_format: Audio format for recording (e.g., s16le)
        audio_rate: Audio sample rate in Hz
        audio_channels: Number of audio channels
        discord_token: Discord bot authentication token (required)
        discord_command_prefix: Prefix for bot commands
        api_host: Host address for the API server
        api_port: Port number for the API server
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Audio configuration
    sink_name: str = "discord_capture"
    audio_format: str = "s16le"
    audio_rate: int = 48000
    audio_channels: int = 2

    # Discord configuration
    discord_token: str
    discord_command_prefix: str = "!"

    # API configuration
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Logging
    log_level: str = "INFO"
