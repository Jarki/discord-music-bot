# loud_bot

## Project Overview

LOUD stands for Local Output Uploaded to Discord

**Python Version:** 3.14.0

## Project Architecture

This is a Discord bot that streams YouTube audio to voice channels. The bot supports:
- Playing music from YouTube URLs or search queries
- Playlist support with queue management
- Multiple playback modes (normal, loop, shuffle)
- Interactive search results selection

## Project Structure

```
loud_bot/
├── src/                              # Main source code
│   ├── bot/                          # Discord bot
│   │   ├── __init__.py
│   │   ├── __main__.py               # Entry point: python -m src.bot
│   │   ├── client.py                 # Discord bot commands
│   │   ├── exc.py                    # Custom exceptions
│   │   ├── utils.py                  # Utility functions
│   │   ├── components/               # Discord UI components
│   │   │   ├── __init__.py
│   │   │   ├── paginated_view.py     # Paginated queue view
│   │   │   └── search_view.py        # Search results selection
│   │   ├── models/                   # Bot data models
│   │   │   ├── __init__.py
│   │   │   └── core.py               # Track, playlist, queue models
│   │   └── dependencies/
│   │       ├── __init__.py
│   │       ├── player.py             # Audio player logic
│   │       ├── player_manager.py     # Per-guild player management
│   │       ├── ytdlp.py              # YouTube audio extraction
│   │       └── queue/                # Queue implementations
│   │           ├── __init__.py
│   │           ├── base.py           # Queue protocol
│   │           └── in_memory.py      # In-memory queue
│   ├── shared/                       # Shared components
│   │   ├── __init__.py
│   │   └── models/
│   │       ├── __init__.py
│   │       └── config.py             # Pydantic settings from .env
│   └── logger_config.py              # Logging configuration
├── tests/                            # Test suite
│   ├── unit/                         # Fast, isolated unit tests (mocked)
│   │   ├── __init__.py
│   │   ├── bot/
│   │   │   └── test_*.py
│   │   └── shared/
│   │       └── test_*.py
│   ├── integration/                  # Integration tests
│   │   ├── __init__.py
│   │   └── test_*.py
│   ├── conftest.py                   # Shared fixtures
│   └── fixtures/
│       └── __init__.py
├── .env                              # Environment variables (gitignored)
├── .env.example                      # Example environment variables
├── pyproject.toml                    # Dependencies & tool config
├── ruff.toml                         # Linting & formatting rules
├── pytest.ini                        # Test configuration
└── AGENTS.md                         # This file
```

## Technology Stack

### Core Dependencies
- **discord.py** - Discord bot library with voice support
- **yt-dlp** - YouTube audio extraction
- **Pydantic** - Configuration management via settings
- **loguru** - Structured logging

### Audio Support
- **PyNaCl** - Voice encryption for Discord
- **FFmpeg** - Audio processing (required by discord.py[voice])

## Configuration

### Pydantic Settings
Configuration is managed via Pydantic Settings and loaded from `.env`:

**`src/shared/models/config.py`:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Discord configuration
    discord_token: str
    discord_command_prefix: str = "!"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

**`.env.example`:**
```
# Discord
DISCORD_TOKEN=your_bot_token_here
DISCORD_COMMAND_PREFIX=!

# Logging
LOG_LEVEL=INFO
```

## Development Setup

```bash
# Install dependencies
uv sync

# Create .env file from example
cp .env.example .env
# Edit .env with your Discord token

# Run the Discord bot
uv run python -m src.bot
```

## Development Commands

All tasks use `uv run poe <task>` via poethepoet:

### Running the Bot
```bash
uv run poe bot               # Start Discord bot
```

### Testing
```bash
uv run poe test              # Run all tests (unit only, mocked)
uv run poe test-cov          # Run tests with coverage report
```

### Code Quality
```bash
uv run poe format            # Format code with ruff
uv run poe format-check      # Check formatting without changes
uv run poe lint              # Lint code with ruff
uv run poe lint-fix          # Lint and auto-fix issues
uv run poe typecheck         # Type check with mypy
```

### Combined Checks
```bash
uv run poe check             # Run all checks (format, lint, typecheck, test)
uv run poe clean             # Clean build artifacts and caches
```

### Manual Tool Usage
```bash
uv run ruff check .          # Lint directly
uv run ruff format .         # Format directly
uv run mypy src              # Type check directly
uv run pytest                # Test directly
```

## Code Standards

### Style & Formatting
- **Line length:** 88 characters (Black-compatible)
- **Formatter:** Ruff (configured in `ruff.toml`)
- **Import sorting:** Managed by Ruff (isort-compatible)
- **Quote style:** Double quotes

### Linting Rules
- Ruff with strict rule sets enabled (see `ruff.toml`)
- Includes: pycodestyle, pyflakes, isort, pep8-naming, pyupgrade, flake8-bugbear
- Auto-fix available for most issues via `uv run poe lint-fix`

### Type Checking
- mypy in strict mode
- All functions should have type hints
- Use `from typing import` for complex types
- Prefer modern type syntax (e.g., `str | None` over `Optional[str]`)

### Testing Requirements
- **Unit tests only** - All external calls must be mocked
- Tests organized by component: `tests/unit/bot/`, `tests/unit/shared/`
- Use pytest fixtures from `conftest.py`
- Test files must match pattern: `test_*.py` or `*_test.py`
- Mock Discord API calls and subprocess calls
- Maintain test coverage (see coverage reports with `uv run poe test-cov`)

## Common Workflows

### Adding a New Feature
1. Create feature branch
2. Write tests first in `tests/unit/<component>/`
3. Mock all external calls (subprocess, Discord API)
4. Implement feature in `src/`
5. Run `uv run poe check` to validate all quality checks
6. Commit changes

### Fixing a Bug
1. Add failing test that reproduces the bug (with mocks)
2. Fix the bug in source code
3. Verify test passes: `uv run poe test`
4. Run full quality check: `uv run poe check`

### Adding Dependencies
```bash
# Add runtime dependency
uv add package-name

# Add development dependency
uv add --dev package-name

# Sync dependencies (after manual pyproject.toml edits)
uv sync
```

### Before Committing
```bash
# Run all quality checks
uv run poe check

# This runs: format-check → lint → typecheck → test
```

## Configuration Files

- **pyproject.toml** - Project metadata, dependencies, Poe tasks, tool configurations
- **ruff.toml** - Ruff linting and formatting rules
- **pytest.ini** - Pytest configuration (test discovery, markers, options)
- **.env** - Environment variables (gitignored, use .env.example as template)

## Notes for AI Assistants

### Quality Standards
- **Always** run `uv run poe check` before considering a task complete
- All code must pass: formatting, linting, type checking, and tests
- Match existing code style and patterns in the project
- All external calls must be mocked in tests

### Code Organization
- New modules go in appropriate `src/` subdirectory (bot/shared)
- Tests mirror source structure: `src/bot/client.py` → `tests/unit/bot/test_client.py`
- Use existing fixtures from `conftest.py` when possible
- Follow the import style: absolute imports from `src`

### Testing Guidelines
- **Use pytest-mock** - Use the `mocker` fixture from pytest-mock instead of `unittest.mock` directly. It provides automatic cleanup and better pytest integration.
- **Mock everything external**: subprocess, Discord API
- Test business logic in isolation
- Use appropriate pytest fixtures
- Prefer parameterized tests for multiple similar cases

### Type Hints
- Add type hints to all function signatures
- Use `typing` module for complex types
- Check against mypy strict mode
- Document complex types with comments if needed
- **Pydantic fields**: Prefer `Annotated[type, Field(...)]` over direct `Field(...)` assignment for better type checking

### Configuration
- Load config via `Settings()` from `src/shared/models/config.py`
- Never hardcode values that should be configurable
- Provide sensible defaults in Settings class
- Document all config options in `.env.example`

### Common Patterns
- Use `uv run python -m src.bot` to run Discord bot
- Use `uv run poe <task>` for development tasks
- Configuration via Pydantic Settings and `.env`
- Follow existing patterns in the codebase for consistency