"""Unit tests for HyprctlService."""

import json
import subprocess

import pytest

from src.api.dependencies.hyprctl_service import HyprctlService
from src.api.models.hyprctl import HyprlandClient


@pytest.fixture
def service() -> HyprctlService:
    """Create a HyprctlService instance for testing."""
    return HyprctlService()


@pytest.fixture
def mock_hyprctl_output() -> str:
    """Mock hyprctl clients -j output with multiple clients."""
    clients = [
        {
            "pid": 1234,
            "title": "Firefox - YouTube",
            "address": "0x12345678",
            "workspace": {"id": 1, "name": "1"},
            "class": "firefox",
            "initialClass": "firefox",
            "size": [1920, 1080],
        },
        {
            "pid": 5678,
            "title": "Spotify",
            "address": "0x87654321",
            "workspace": {"id": 2, "name": "2"},
            "class": "spotify",
            "initialClass": "spotify",
            "size": [1280, 720],
        },
    ]
    return json.dumps(clients)


def test_get_clients_success(
    service: HyprctlService, mock_hyprctl_output: str, mocker
) -> None:
    """Test successful parsing of hyprctl output with multiple clients."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = mocker.MagicMock(stdout=mock_hyprctl_output)

    clients = service.get_clients()

    assert len(clients) == 2
    assert clients[0].pid == 1234
    assert clients[0].title == "Firefox - YouTube"
    assert clients[1].pid == 5678
    assert clients[1].title == "Spotify"

    # Verify subprocess was called correctly
    mock_run.assert_called_once_with(
        ["hyprctl", "clients", "-j"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )


def test_get_clients_empty_list(service: HyprctlService, mocker) -> None:
    """Test handling of empty client list."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = mocker.MagicMock(stdout="[]")

    clients = service.get_clients()

    assert clients == []


def test_get_clients_command_failure(service: HyprctlService, mocker) -> None:
    """Test handling of command execution failure."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["hyprctl", "clients", "-j"],
        stderr="Command failed",
    )

    with pytest.raises(RuntimeError, match="hyprctl command failed"):
        service.get_clients()


def test_get_clients_invalid_json(service: HyprctlService, mocker) -> None:
    """Test handling of invalid JSON output."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = mocker.MagicMock(stdout="invalid json {")

    with pytest.raises(RuntimeError, match="Failed to parse hyprctl JSON output"):
        service.get_clients()


def test_get_clients_missing_pid_field(service: HyprctlService, mocker) -> None:
    """Test handling of missing pid field in JSON."""
    mock_run = mocker.patch("subprocess.run")
    clients = [{"title": "Firefox"}]  # Missing pid
    mock_run.return_value = mocker.MagicMock(stdout=json.dumps(clients))

    with pytest.raises(RuntimeError, match="Missing required field in hyprctl output"):
        service.get_clients()


def test_get_clients_missing_title_field(service: HyprctlService, mocker) -> None:
    """Test handling of missing title field in JSON."""
    mock_run = mocker.patch("subprocess.run")
    clients = [{"pid": 1234}]  # Missing title
    mock_run.return_value = mocker.MagicMock(stdout=json.dumps(clients))

    with pytest.raises(RuntimeError, match="Missing required field in hyprctl output"):
        service.get_clients()


def test_get_clients_hyprctl_not_found(service: HyprctlService, mocker) -> None:
    """Test handling of hyprctl command not found."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = FileNotFoundError("hyprctl not found")

    with pytest.raises(FileNotFoundError):
        service.get_clients()


def test_get_clients_timeout(service: HyprctlService, mocker) -> None:
    """Test handling of command timeout."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd=["hyprctl", "clients", "-j"],
        timeout=5,
    )

    with pytest.raises(subprocess.TimeoutExpired):
        service.get_clients()


def test_get_clients_custom_timeout(mocker) -> None:
    """Test that custom timeout is passed to subprocess."""
    service = HyprctlService(timeout=10)
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = mocker.MagicMock(stdout="[]")

    service.get_clients()

    # Verify custom timeout was used
    mock_run.assert_called_once_with(
        ["hyprctl", "clients", "-j"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_get_clients_extracts_only_pid_and_title(
    service: HyprctlService,
    mocker,
) -> None:
    """Test that only pid and title are extracted from hyprctl output."""
    mock_run = mocker.patch("subprocess.run")
    clients = [
        {
            "pid": 1234,
            "title": "Test Window",
            "address": "0x12345678",
            "workspace": {"id": 1},
            "class": "test",
            "extra_field": "should be ignored",
        }
    ]
    mock_run.return_value = mocker.MagicMock(stdout=json.dumps(clients))

    result = service.get_clients()

    assert len(result) == 1
    assert isinstance(result[0], HyprlandClient)
    assert result[0].pid == 1234
    assert result[0].title == "Test Window"
    # Verify no extra fields are present
    assert not hasattr(result[0], "address")
    assert not hasattr(result[0], "workspace")
    assert not hasattr(result[0], "class")
