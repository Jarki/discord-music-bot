# loud_bot

## Project Overview

LOUD stands for Local Output Uploaded to Discord

**Python Version:** 3.14.0

## Project Architecture

This project consists of two independently runnable components:
- **API Server**: FastAPI-based REST API for audio source discovery and routing
- **Discord Bot**: discord.py bot for voice channel streaming

Both components share common dependencies and configuration.

## Project Structure

```
loud_bot/
├── src/                              # Main source code
│   ├── __init__.py
│   ├── api/                          # FastAPI server
│   │   ├── __init__.py
│   │   ├── __main__.py               # Entry point: python -m src.api
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   └── audio.py              # Audio discovery endpoints
|   |   ├── models/                   # Any models required for the api
│   │   └── dependencies/
│   │       ├── __init__.py
│   │       └── discovery_service.py  # Audio source discovery logic
│   ├── bot/                          # Discord bot
│   │   ├── __init__.py
│   │   ├── __main__.py               # Entry point: python -m src.bot
│   │   ├── client.py                 # Discord bot commands
|   |   ├── models/                   # Any models required for the bot
│   │   └── dependencies/
│   │       ├── __init__.py
│   │       ├── audio_monitor.py      # Read-only monitor access
│   │       └── recorder.py           # AudioSource implementation
│   └── shared/                       # Shared components
│       ├── __init__.py
│       ├── dependencies/
│       │   ├── __init__.py
│       │   └── virtual_sink.py       # Sink management (full + readonly)
│       ├── models/
│       │   ├── __init__.py
│       │   └── config.py             # Pydantic settings from .env
│       └── logging.py                # Shared logging configuration
├── tests/                            # Test suite
│   ├── unit/                         # Fast, isolated unit tests (mocked)
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   └── test_*.py
│   │   ├── bot/
│   │   │   └── test_*.py
│   │   └── shared/
│   │       └── test_*.py
│   └── conftest.py                   # Shared fixtures for all tests
├── .env                              # Environment variables (gitignored)
├── .env.example                      # Example environment variables
├── pyproject.toml                    # Dependencies & tool config
├── ruff.toml                         # Linting & formatting rules
├── pytest.ini                        # Test configuration
└── AGENTS.md                         # This file
```

## Technology Stack

### Core Dependencies
- **FastAPI** - REST API framework
- **discord.py** - Discord bot library
- **Pydantic** - Configuration management via settings
- **uvicorn** - ASGI server for FastAPI

### System Dependencies
- **PulseAudio/PipeWire** - Audio routing (`pactl`, `parec`)
- **Hyprland** - Window manager for client metadata (`hyprctl`)

### No Audio Processing Libraries
Audio is captured as raw PCM from system sources - no additional audio processing libraries needed.

## Configuration

### Pydantic Settings
Configuration is managed via Pydantic Settings and loaded from `.env`:

**`src/shared/models/config.py`:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

**`.env.example`:**
```
# Discord
DISCORD_TOKEN=your_bot_token_here
DISCORD_COMMAND_PREFIX=!

# Audio
SINK_NAME=discord_capture
AUDIO_FORMAT=s16le
AUDIO_RATE=48000
AUDIO_CHANNELS=2

# API
API_HOST=127.0.0.1
API_PORT=8000

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

# Run the API server
uv run python -m src.api

# Run the Discord bot (in separate terminal)
uv run python -m src.bot
```

## Development Commands

All tasks use `uv run poe <task>` via poethepoet:

### Running Services
```bash
uv run poe api               # Start FastAPI server
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
- Tests organized by component: `tests/unit/api/`, `tests/unit/bot/`, `tests/unit/shared/`
- Use pytest fixtures from `conftest.py`
- Test files must match pattern: `test_*.py` or `*_test.py`
- Mock `pactl`, `hyprctl`, Discord API calls, and subprocess calls
- Maintain test coverage (see coverage reports with `uv run poe test-cov`)

## System Architecture

### Audio Pipeline

```
1. Application (Brave/Spotify) produces audio
   ↓
2. Routed to null sink (discord_capture)
   ↓
3. Monitor source (discord_capture.monitor)
   ↓
4. parec captures raw PCM
   ↓
5. Recorder feeds to Discord bot
   ↓
6. Discord voice channel
```

### Component Interaction

```
API Server:
  - Creates/manages null sink via SinkManager
  - Scans audio sources (pactl list sink-inputs)
  - Gets window titles (hyprctl clients)
  - Routes selected source to null sink
  - Exposes REST endpoints

Discord Bot:
  - Uses ReadOnlySink (cannot modify sink)
  - Joins voice channel on command
  - Creates Recorder when streaming
  - Reads from monitor source via parec
  - Streams PCM to Discord
```

### Shared Dependencies

**VirtualSink Classes:**
- `SinkManager` - Full control (create, destroy, route)
- `ReadOnlySink` - Wrapper that raises errors on write operations

**Usage:**
- API uses `SinkManager` for full lifecycle management
- Bot uses `ReadOnlySink` for safe read-only access

## Common Workflows

### Adding a New Feature
1. Create feature branch
2. Write tests first in `tests/unit/<component>/`
3. Mock all external calls (pactl, hyprctl, subprocess, Discord API)
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

## Development Roadmap

The system will be built incrementally through the following phases:

### Phase 1: Foundation
**Goal:** Establish core infrastructure and shared dependencies

**Components:**
- Virtual sink management (create, destroy, route audio)
- Configuration model with Pydantic Settings
- Shared logging setup
- Integration tests for audio system

**Deliverables:**
- Working sink manager with full and read-only modes
- Type-safe configuration from .env
- Consistent logging across services

### Phase 2: API Server
**Goal:** Build REST API for audio source discovery and routing

**Components:**
- FastAPI app with lifecycle management
- Hyprland client discovery (hyprctl integration)
- PulseAudio sink-input discovery (pactl integration)
- Audio source selection and routing endpoints

**Deliverables:**
- Running API server with documented endpoints
- Ability to list audio sources with window titles
- Ability to route selected audio to virtual sink

### Phase 3: Discord Bot
**Goal:** Implement Discord bot for voice channel streaming

**Components:**
- Discord.py bot client with commands
- Audio recorder (parec integration)
- Voice channel management
- Read-only sink access

**Deliverables:**
- Bot that joins voice channels on command
- Streams audio from virtual sink to Discord
- Clean lifecycle management

### Phase 4: Integration & Polish
**Goal:** Connect all components and refine user experience

**Components:**
- End-to-end workflow testing
- Error handling and edge cases
- Documentation and examples
- Performance optimization

**Deliverables:**
- Complete workflow: select audio → route → stream to Discord
- Comprehensive documentation
- Production-ready system

### Development Principles
- **Build incrementally** - Each phase produces working components
- **Test as you go** - Unit tests for all business logic
- **Integration points** - Phases connect through well-defined interfaces
- **Iterative refinement** - Features can be enhanced in later phases

## Notes for AI Assistants

### Quality Standards
- **Always** run `uv run poe check` before considering a task complete
- All code must pass: formatting, linting, type checking, and tests
- Match existing code style and patterns in the project
- All external calls must be mocked in tests

### Code Organization
- New modules go in appropriate `src/` subdirectory (api/bot/shared)
- Tests mirror source structure: `src/api/routes/audio.py` → `tests/unit/api/test_audio.py`
- Use existing fixtures from `conftest.py` when possible
- Follow the import style: absolute imports from `src`

### Testing Guidelines
- **Use pytest-mock** - Use the `mocker` fixture from pytest-mock instead of `unittest.mock` directly. It provides automatic cleanup and better pytest integration.
- **Mock everything external**: subprocess, pactl, hyprctl, Discord API
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
- Use `uv run python -m src.api` to run API server
- Use `uv run python -m src.bot` to run Discord bot
- Use `uv run poe <task>` for development tasks
- Configuration via Pydantic Settings and `.env`
- Follow existing patterns in the codebase for consistency
- Both services are independent but share common dependencies