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

YouTube extraction uses `yt-dlp[default,deno]>=2026.10.21`. Run
`uv sync --locked` to install the locked extractor, EJS challenge-solving
components, and Deno runtime. FFmpeg must also be installed.

Queued tracks retain their original YouTube page URLs. The bot resolves fresh
media immediately before playback rather than reusing expiring stream links.
Required extractor HTTP headers are forwarded to FFmpeg for playback.

### Playback and queue behavior

- Search returns at most five selectable results. A selection is claimed once,
  and controls are disabled before slow extraction.
- Playlists use only their first 100 entries. A requested start index outside
  that retained range is rejected instead of reporting that nothing was queued
  as a successful addition.
- The queue holds at most 256 entries. Normal mode removes consumed entries;
  repeat and shuffle modes retain their collection.
- Unavailable tracks are skipped. Consecutive failures stop after one bounded
  traversal rather than retrying a broken repeating queue indefinitely.
- Clear and leave invalidate pending playback and obsolete completion callbacks.
  Skipping preserves the newly started current track.
- Join/play can connect an idle bot, but commands do not move an active bot
  between voice channels. Playback mutations require the caller to be in the
  bot's voice channel; queue/current inspection remains read-only.

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
- `/skip [songs]` - Skip 1–256 tracks, stopping at queue exhaustion
- `/pause` - Pause playback
- `/resume` - Resume playback
- `/current` - Show currently playing track
- `/queue` - Display the queue
- `/clear` - Clear the queue
- `/mode <no_repeat|repeat_queue|repeat_single|shuffle>` - Set playback mode

## Pi deployment

The manual **Deploy Dev** and **Deploy Prod** GitHub Actions workflows use the
same `[self-hosted, pi]` runner labels as `idontwant_toopen_insta`. The runner must
be available to this repository and have Docker with Compose/Buildx support.
Production also uses QEMU for cross-platform builds.

| Environment | Runner-local configuration | Compose project | Published platforms |
| --- | --- | --- | --- |
| Dev | `$HOME/deploy/loud-bot-dev/.env` | `loud-bot-dev` | `linux/arm64` |
| Prod | `$HOME/deploy/loud-bot-prod/.env` | `loud-bot-prod` | `linux/amd64`, `linux/arm64` |

Before dispatching, create the appropriate runner-local `.env` using
`.env.example`, set `DISCORD_TOKEN`, and restrict its permissions (`chmod 600`).
Use a **separate Discord application/token for dev** so both deployments do not
control the same bot. Tokens are not committed or supplied as workflow inputs.
An inherited runner `DISCORD_TOKEN` cannot override the deployment-local token.

In GitHub Actions, choose the workflow and a trusted Git ref. Optional
`compose_ref` selects the ref for **both** the image and Compose file;
`image_tag` sets a published alias: `latest` by default for dev, `prod` for prod.
The workflow logs in to GHCR with `GITHUB_TOKEN`, builds and pushes an
environment-specific image, then deploys its immutable digest with
`docker compose pull` and `up --wait`.
Each environment has its own deployment concurrency group, image repository,
directory, and Compose project.

For local Docker use, set up `.env` and run `docker compose up --build -d`.
Without `LOUD_BOT_IMAGE`, Compose uses `loud-bot:local`; deployed runs supply
the GHCR digest. Container readiness does not prove successful Discord login:
check the bot's logs and voice behavior after deployment.


## Development

First, install all of the dependencies:

```bash
uv sync --all-groups
```

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
