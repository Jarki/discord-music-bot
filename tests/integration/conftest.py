"""Fixtures for integration tests.

These fixtures are available to all integration tests and provide
common functionality for testing with real system dependencies.
"""

import subprocess
import uuid
from collections.abc import Generator

import pytest


@pytest.fixture(scope="session")
def pulseaudio_available() -> bool:
    """Check if PulseAudio/PipeWire is available on the system.

    This fixture runs once per test session and checks if the pactl
    command is available and can connect to the audio server.

    Returns:
        True if PulseAudio/PipeWire is available

    Raises:
        pytest.skip: If audio system is not available
    """
    try:
        subprocess.run(
            ["pactl", "info"], check=True, capture_output=True, text=True, timeout=5
        )
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        pytest.skip("PulseAudio/PipeWire not available on this system")


@pytest.fixture
def unique_sink_name() -> str:
    """Generate a unique sink name for test isolation.

    Each test gets its own unique sink name to prevent interference
    between parallel or sequential tests.

    Returns:
        A unique sink name like "test_sink_a1b2c3d4"
    """
    return f"test_sink_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module", autouse=True)
def cleanup_after_all_tests() -> Generator[None]:
    """Cleanup any leftover test sinks after all tests complete.

    This fixture runs automatically after all tests in a module complete
    and ensures no test sinks are left in the system.

    Yields:
        None - tests run here
    """
    yield

    # Cleanup any leftover test sinks
    try:
        result = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Find any test sinks
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("test_sink_"):
                # Try to unload the module
                try:
                    # Get the module index
                    module_result = subprocess.run(
                        ["pactl", "list", "short", "modules"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    for module_line in module_result.stdout.strip().split("\n"):
                        if parts[1] in module_line:
                            module_parts = module_line.split()
                            if module_parts:
                                subprocess.run(
                                    ["pactl", "unload-module", module_parts[0]],
                                    check=False,
                                    timeout=5,
                                )
                                break
                except Exception:
                    pass  # Ignore cleanup errors
    except Exception:
        pass  # Ignore cleanup errors
