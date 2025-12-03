"""Integration tests for HyprctlService.

These tests interact with the actual Hyprland system to verify
real-world behavior of the HyprctlService.

Requirements:
- Hyprland must be installed and running
- `hyprctl` command must be available
- Tests will execute real hyprctl commands
"""

import subprocess

import pytest

from src.api.dependencies.hyprctl_service import HyprctlService
from src.api.models.hyprctl import HyprlandClient


@pytest.fixture(scope="session")
def hyprland_available() -> bool:
    """Check if Hyprland is available on the system.

    This fixture runs once per test session and checks if the hyprctl
    command is available and can connect to Hyprland.

    Returns:
        True if Hyprland is available

    Raises:
        pytest.skip: If Hyprland is not available
    """
    try:
        # Try to run hyprctl version to check if it's available
        subprocess.run(
            ["hyprctl", "version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        pytest.skip("Hyprland not available on this system")


@pytest.fixture
def hyprctl_service() -> HyprctlService:
    """Create a HyprctlService instance for integration testing."""
    return HyprctlService(timeout=10)  # Longer timeout for integration tests


def test_hyprctl_service_integration(
    hyprctl_service: HyprctlService, hyprland_available: bool
) -> None:
    """Integration test for HyprctlService with real hyprctl command.

    This test verifies that the service can successfully:
    1. Execute the hyprctl clients -j command
    2. Parse the JSON output
    3. Return valid HyprlandClient objects

    Args:
        hyprctl_service: The service instance to test
        hyprland_available: Fixture ensuring Hyprland is available
    """
    # Execute the real hyprctl command
    clients = hyprctl_service.get_clients()

    # Verify we got a list
    assert isinstance(clients, list)

    # Verify each item is a HyprlandClient
    for client in clients:
        assert isinstance(client, HyprlandClient)
        assert isinstance(client.pid, int)
        assert client.pid > 0  # PIDs should be positive
        assert isinstance(client.title, str)
        # Title can be empty but should exist
        assert hasattr(client, "title")


def test_hyprctl_service_returns_clients_with_valid_data(
    hyprctl_service: HyprctlService, hyprland_available: bool
) -> None:
    """Test that returned clients have realistic data.

    This test verifies that the clients returned by hyprctl have
    reasonable values that look like real window information.

    Args:
        hyprctl_service: The service instance to test
        hyprland_available: Fixture ensuring Hyprland is available
    """
    clients = hyprctl_service.get_clients()

    # If there are no clients, that's fine (system might have no windows)
    if not clients:
        return

    # Check that we have at least some basic validation
    for client in clients:
        # PID should be a reasonable number (not negative, within Linux PID range)
        assert 1 <= client.pid <= 4194304  # Linux PID max is 2^22

        # Title should be a string (can be empty for some windows)
        assert isinstance(client.title, str)

        # Most windows should have non-empty titles, but some might not
        # We don't enforce this as it's system-dependent


def test_hyprctl_service_handles_empty_client_list(
    hyprctl_service: HyprctlService, hyprland_available: bool
) -> None:
    """Test that the service handles cases with no windows gracefully.

    This might happen if Hyprland is running but no windows are open.

    Args:
        hyprctl_service: The service instance to test
        hyprland_available: Fixture ensuring Hyprland is available
    """
    clients = hyprctl_service.get_clients()

    # Should return an empty list, not None or raise an exception
    assert clients == [] or isinstance(clients, list)
