# loud_bot

A Discord bot that streams YouTube audio to voice channels.

LOUD stands for Local Output Uploaded to Discord

> **⚠️ Educational Purpose Only**
> This project is intended for educational purposes and personal use only. It demonstrates Discord bot development and audio streaming techniques. Users are responsible for ensuring their usage complies with YouTube's Terms of Service and local laws. This bot is not intended for commercial use or public deployment.

## Features

- 🎵 Play music from YouTube URLs or search queries
- 📋 Playlist support with queue management
- 🔀 Multiple playback modes (normal, loop, shuffle)
- 🔍 Interactive search results selection
- ⏭️ Queue controls (skip, pause, resume, clear)

## Installation and Usage

This project uses [uv](https://docs.astral.sh/uv/) for dependency management:

```bash
# Install dependencies
uv sync

# Create .env file from example
cp .env.example .env
# Edit .env and add your Discord bot token

# Run the bot
uv run python -m src.bot
```

## Required Setup

1. Create a Discord bot at https://discord.com/developers/applications
2. Enable the following in Bot settings:
   - Message Content Intent
   - Server Members Intent
   - Presence Intent
3. Invite the bot to your server with appropriate permissions
4. Install FFmpeg (required for audio playback)

## Bot Commands

- `/join` - Join your voice channel
- `/leave` - Leave the voice channel
- `/play <song>` - Play a song from URL or search query
- `/skip [songs]` - Skip current track or multiple tracks
- `/pause` - Pause playback
- `/resume` - Resume playback
- `/current` - Show currently playing track
- `/queue` - Display the queue
- `/clear` - Clear the queue
- `/mode <normal|loop|shuffle>` - Set playback mode

## Development

First, install all of the dependencies:

```uv run sync --all-groups```

### Tools

- **uv**: Fast Python package installer and resolver
- **ruff**: Lightning-fast linter and formatter
- **mypy**: Static type checker
- **poethepoet**: Task runner for common development tasks
- **pytest**: Testing framework

### Development Tasks

Run tasks using `poe` (poethepoet):

```bash
# Run tests
uv run poe test

# Format code
uv run poe format

# Check formatting (without changes)
uv run poe format-check

# Lint code
uv run poe lint

# Lint and auto-fix issues
uv run poe lint-fix

# Type check
uv run poe typecheck

# Run all quality checks (format, lint, typecheck, test)
uv run poe check
```

### Manual Tool Usage

```bash
# Run ruff
uv run ruff check .
uv run ruff format .

# Run mypy
uv run mypy src

# Run pytest
uv run pytest
```
