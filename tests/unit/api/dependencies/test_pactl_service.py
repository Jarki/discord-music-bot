"""Unit tests for PactlService."""

import subprocess

import pytest

from src.api.dependencies.pactl_service import PactlService
from src.api.models.pactl import SinkInput


class TestPactlService:
    """Test PactlService class."""

    def test_get_sink_inputs_success(self, mocker) -> None:
        """Test successful parsing of multiple sink-inputs."""
        mock_output = """Sink Input #42
	Driver: protocol-native.c
	Owner Module: 10
	Client: 123
	Sink: 0
	Properties:
		application.name = "Firefox"
		application.process.id = "12345"
		media.name = "YouTube - Video Title"

Sink Input #43
	Driver: protocol-native.c
	Owner Module: 11
	Client: 124
	Sink: 1
	Properties:
		application.name = "Spotify"
		application.process.id = "67890"
		media.name = "Song Title"
"""

        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = mocker.Mock(stdout=mock_output, stderr="")

        service = PactlService()
        result = service.get_sink_inputs()

        assert len(result) == 2
        assert result[0] == SinkInput(
            sink_input_id=42, pid=12345, application_name="Firefox"
        )
        assert result[1] == SinkInput(
            sink_input_id=43, pid=67890, application_name="Spotify"
        )

        mock_run.assert_called_once_with(
            ["pactl", "list", "sink-inputs"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )

    def test_get_sink_inputs_empty_list(self, mocker) -> None:
        """Test handling of no sink-inputs (no audio playing)."""
        mock_output = ""

        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = mocker.Mock(stdout=mock_output, stderr="")

        service = PactlService()
        result = service.get_sink_inputs()

        assert result == []

    def test_get_sink_inputs_command_failure(self, mocker) -> None:
        """Test handling of command failure."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["pactl", "list", "sink-inputs"],
            stderr="Connection refused",
        )

        service = PactlService()

        with pytest.raises(RuntimeError) as exc_info:
            service.get_sink_inputs()

        assert "Failed to run pactl command" in str(exc_info.value)
        assert "Connection refused" in str(exc_info.value)

    def test_get_sink_inputs_malformed_output(self, mocker) -> None:
        """Test handling of malformed output (skip malformed entries)."""
        mock_output = """Sink Input #42
	Properties:
		application.name = "Firefox"
		application.process.id = "12345"

Sink Input #43
	Properties:
		application.name = "Spotify"
		# Missing PID - this entry should be skipped

Sink Input #44
	Properties:
		application.process.id = "99999"
		# Missing name - this entry should be skipped

Sink Input #45
	Properties:
		application.name = "Valid App"
		application.process.id = "11111"
"""

        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = mocker.Mock(stdout=mock_output, stderr="")

        service = PactlService()
        result = service.get_sink_inputs()

        # Only entries with both pid and name should be included
        assert len(result) == 2
        assert result[0] == SinkInput(
            sink_input_id=42, pid=12345, application_name="Firefox"
        )
        assert result[1] == SinkInput(
            sink_input_id=45, pid=11111, application_name="Valid App"
        )

    def test_get_sink_inputs_missing_required_fields(self, mocker) -> None:
        """Test handling of sink-inputs missing required fields."""
        mock_output = """Sink Input #42
	Properties:
		media.name = "Some Audio"
"""

        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = mocker.Mock(stdout=mock_output, stderr="")

        service = PactlService()
        result = service.get_sink_inputs()

        # Entry without pid and name should be skipped
        assert result == []

    def test_get_sink_inputs_pactl_not_found(self, mocker) -> None:
        """Test handling when pactl command is not found."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("pactl not found")

        service = PactlService()

        with pytest.raises(FileNotFoundError):
            service.get_sink_inputs()

    def test_get_sink_inputs_timeout(self, mocker) -> None:
        """Test handling of command timeout."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["pactl", "list", "sink-inputs"], timeout=5
        )

        service = PactlService()

        with pytest.raises(subprocess.TimeoutExpired):
            service.get_sink_inputs()

    def test_custom_timeout_passed_to_subprocess(self, mocker) -> None:
        """Test that custom timeout is passed to subprocess."""
        mock_output = ""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = mocker.Mock(stdout=mock_output, stderr="")

        service = PactlService(timeout=10)
        service.get_sink_inputs()

        mock_run.assert_called_once_with(
            ["pactl", "list", "sink-inputs"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )

    def test_parse_with_varied_spacing(self, mocker) -> None:
        """Test parsing with varied whitespace and formatting."""
        mock_output = """Sink Input #100
	Properties:
		application.name = "Edge"
		application.process.id = "55555"
"""

        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = mocker.Mock(stdout=mock_output, stderr="")

        service = PactlService()
        result = service.get_sink_inputs()

        assert len(result) == 1
        assert result[0] == SinkInput(
            sink_input_id=100, pid=55555, application_name="Edge"
        )
