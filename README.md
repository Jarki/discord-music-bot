# loud_bot

LOUD stands for Local Output Uploaded to Discord

## Installation and Usage

This project uses [uv](https://docs.astral.sh/uv/) for dependency management:

```bash
# Install dependencies
uv sync

# Run the application
uv run python -m src
```

## Development

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
