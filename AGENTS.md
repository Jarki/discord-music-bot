# loud_bot

## Project Overview

LOUD stands for Local Output Uploaded to Discord

**Python Version:** 3.14.0

## Project Structure

```
loud_bot/
├── src/                              # Main source code
│   ├── __init__.py
│   └── __main__.py
├── tests/                            # Test suite
│   ├── unit/                         # Fast, isolated unit tests
│   │   ├── __init__.py
│   │   └── test_*.py
│   ├── integration/                  # Tests with external dependencies
│   │   ├── __init__.py
│   │   └── test_*.py
│   ├── e2e/                          # End-to-end tests (optional)
│   │   ├── __init__.py
│   │   └── test_*.py
│   └── conftest.py                   # Shared fixtures for all tests
├── pyproject.toml                    # Dependencies & tool config
├── ruff.toml                         # Linting & formatting rules
├── pytest.ini                        # Test configuration
└── AGENTS.md                         # This file
```

### Test Directory Guidelines

- **`tests/unit/`** - Fast tests with no external dependencies (database, API, filesystem)
  - Mock external services
  - Test pure functions and business logic
  - Should run in milliseconds
  
- **`tests/integration/`** - Tests that interact with external systems
  - Database queries
  - External API calls
  - File I/O operations
  - May take seconds to run
  
- **`tests/e2e/`** - Full workflow tests (optional)
  - Complete user scenarios
  - Multiple components working together
  - Slowest tests, run less frequently
  
- **`tests/conftest.py`** - Shared pytest fixtures
  - Session-scoped fixtures (run once)
  - Function-scoped fixtures (run per test)
  - Auto-applied markers based on directory

## Development Setup

```bash
# Install dependencies
uv sync

# Run the application
uv run python -m src
```

## Development Commands

All tasks use `uv run poe <task>` via poethepoet:

### Testing
```bash
uv run poe test              # Run all tests
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
- mypy in strict mode (if configured)
- All functions should have type hints
- Use `from typing import` for complex types
- Prefer `Optional[T]` over `T | None` for clarity (unless Python 3.10+)

### Testing Requirements
- Tests organized by type: `tests/unit/` and `tests/integration/`
- Use pytest fixtures from `conftest.py`
- Test files must match pattern: `test_*.py` or `*_test.py`
- Maintain test coverage (see coverage reports with `uv run poe test-cov`)

## Common Workflows

### Adding a New Feature
1. Create feature branch
2. Write tests first in appropriate directory (`tests/unit/` or `tests/integration/`)
3. Implement feature in `src/`
4. Run `uv run poe check` to validate all quality checks
5. Commit changes

### Fixing a Bug
1. Add failing test that reproduces the bug
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
- **mypy.ini** - mypy type checking configuration (if exists)

## Test Organization

### Test Markers
Tests can be marked for selective execution (defined in `pytest.ini`):
- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Tests with external dependencies
- `@pytest.mark.slow` - Tests that take >1 second
- `@pytest.mark.smoke` - Quick smoke tests

### Running Specific Tests
```bash
# Run only unit tests
uv run pytest tests/unit/

# Run only integration tests  
uv run pytest tests/integration/

# Run tests by marker
uv run pytest -m unit
uv run pytest -m "not slow"
```

## Notes for AI Assistants

### Quality Standards
- **Always** run `uv run poe check` before considering a task complete
- All code must pass: formatting, linting, type checking, and tests
- Match existing code style and patterns in the project

### Code Organization
- New modules go in `src/`
- Tests mirror source structure: `src/module.py` → `tests/unit/test_module.py`
- Use existing fixtures from `conftest.py` when possible
- Follow the import style: absolute imports from `src`

### Testing Guidelines
- Write unit tests for business logic (fast, no I/O)
- Write integration tests for external dependencies (database, APIs, files)
- Use appropriate pytest markers
- Prefer parameterized tests for multiple similar cases

### Type Hints
- Add type hints to all function signatures
- Use `typing` module for complex types
- Check against mypy strict mode
- Document complex types with comments if needed

### Common Patterns
- Use `uv run python -m src` to run the application
- Use `uv run poe <task>` for development tasks
- Configuration via environment variables or config files
- Follow existing patterns in the codebase for consistency