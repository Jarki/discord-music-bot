"""Unit tests for the SinkRecorder class.

These tests use pytest-mock to mock subprocess calls and test the recorder's
logic without requiring actual audio system access.
"""

import subprocess
from unittest.mock import MagicMock

import pytest

from src.bot.dependencies.recorder import SinkRecorder


class TestSinkRecorderInit:
    """Test SinkRecorder initialization."""

    def test_init_default_parameters(self) -> None:
        """Test recorder initialization with default parameters."""
        recorder = SinkRecorder("test_monitor.monitor")

        assert recorder.monitor_source == "test_monitor.monitor"
        assert recorder.audio_format == "s16le"
        assert recorder.audio_rate == 48000
        assert recorder.audio_channels == 2
        assert recorder.process is None
        assert not recorder._started

    def test_init_custom_parameters(self) -> None:
        """Test recorder initialization with custom parameters."""
        recorder = SinkRecorder(
            monitor_source="custom_monitor",
            audio_format="s24le",
            audio_rate=44100,
            audio_channels=1,
        )

        assert recorder.monitor_source == "custom_monitor"
        assert recorder.audio_format == "s24le"
        assert recorder.audio_rate == 44100
        assert recorder.audio_channels == 1


class TestSinkRecorderStart:
    """Test SinkRecorder start() method."""

    def test_start_creates_subprocess_with_correct_command(
        self, mocker: MagicMock
    ) -> None:
        """Test that start() creates subprocess with correct parec command."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()

        expected_command = [
            "parec",
            "-d",
            "test_monitor.monitor",
            "--format=s16le",
            "--rate=48000",
            "--channels=2",
        ]

        mock_popen.assert_called_once_with(
            expected_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert recorder._started
        assert recorder.process is mock_process

    def test_start_with_custom_parameters(self, mocker: MagicMock) -> None:
        """Test start() with custom audio parameters."""
        mock_popen = mocker.patch("subprocess.Popen")

        recorder = SinkRecorder(
            monitor_source="custom_monitor",
            audio_format="s24le",
            audio_rate=44100,
            audio_channels=1,
        )
        recorder.start()

        expected_command = [
            "parec",
            "-d",
            "custom_monitor",
            "--format=s24le",
            "--rate=44100",
            "--channels=1",
        ]

        mock_popen.assert_called_once()
        actual_command = mock_popen.call_args[0][0]
        assert actual_command == expected_command

    def test_start_raises_file_not_found_when_parec_missing(
        self, mocker: MagicMock
    ) -> None:
        """Test that start() raises FileNotFoundError when parec is not installed."""
        mocker.patch("subprocess.Popen", side_effect=FileNotFoundError())

        recorder = SinkRecorder("test_monitor.monitor")

        with pytest.raises(FileNotFoundError, match="parec command not found"):
            recorder.start()

        assert not recorder._started

    def test_start_raises_error_on_subprocess_failure(self, mocker: MagicMock) -> None:
        """Test that start() raises SubprocessError on other failures."""
        mocker.patch("subprocess.Popen", side_effect=OSError("Permission denied"))

        recorder = SinkRecorder("test_monitor.monitor")

        with pytest.raises(subprocess.SubprocessError, match="Failed to start parec"):
            recorder.start()

        assert not recorder._started

    def test_start_raises_error_if_already_started(self, mocker: MagicMock) -> None:
        """Test that start() raises RuntimeError if already started."""
        mocker.patch("subprocess.Popen")

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()

        with pytest.raises(RuntimeError, match="already started"):
            recorder.start()


class TestSinkRecorderRead:
    """Test SinkRecorder read() method."""

    def test_read_returns_correct_frame_size(self, mocker: MagicMock) -> None:
        """Test that read() returns exactly 3,840 bytes."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"x" * 3840
        mock_process.stdout = mock_stdout
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()

        data = recorder.read()

        assert len(data) == 3840
        assert data == b"x" * 3840
        mock_stdout.read.assert_called_once_with(3840)

    def test_read_returns_empty_bytes_if_not_started(self) -> None:
        """Test that read() returns empty bytes if recorder not started."""
        recorder = SinkRecorder("test_monitor.monitor")

        data = recorder.read()

        assert data == b""

    def test_read_returns_empty_bytes_if_process_is_none(
        self, mocker: MagicMock
    ) -> None:
        """Test that read() returns empty bytes if process is None."""
        recorder = SinkRecorder("test_monitor.monitor")
        recorder._started = True  # Manually set started without creating process
        recorder.process = None

        data = recorder.read()

        assert data == b""

    def test_read_returns_empty_bytes_on_eof(self, mocker: MagicMock) -> None:
        """Test that read() returns empty bytes when EOF is reached."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_stdout = MagicMock()
        # Simulate EOF by returning less than requested
        mock_stdout.read.return_value = b"x" * 100
        mock_process.stdout = mock_stdout
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()

        data = recorder.read()

        assert data == b""

    def test_read_handles_read_exception_gracefully(self, mocker: MagicMock) -> None:
        """Test that read() handles read exceptions by returning empty bytes."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.read.side_effect = OSError("Read error")
        mock_process.stdout = mock_stdout
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()

        data = recorder.read()

        assert data == b""

    def test_read_multiple_frames(self, mocker: MagicMock) -> None:
        """Test reading multiple frames in sequence."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_stdout = MagicMock()
        # Return different data each time
        mock_stdout.read.side_effect = [b"a" * 3840, b"b" * 3840, b"c" * 3840]
        mock_process.stdout = mock_stdout
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()

        data1 = recorder.read()
        data2 = recorder.read()
        data3 = recorder.read()

        assert data1 == b"a" * 3840
        assert data2 == b"b" * 3840
        assert data3 == b"c" * 3840
        assert mock_stdout.read.call_count == 3


class TestSinkRecorderCleanup:
    """Test SinkRecorder cleanup() method."""

    def test_cleanup_terminates_process(self, mocker: MagicMock) -> None:
        """Test that cleanup() terminates the subprocess."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()
        recorder.cleanup()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()
        assert not recorder._started
        assert recorder.process is None

    def test_cleanup_kills_process_on_timeout(self, mocker: MagicMock) -> None:
        """Test that cleanup() kills process if terminate times out."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        # First wait() times out, second wait() succeeds
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("parec", 5), None]
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()
        recorder.cleanup()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        assert mock_process.wait.call_count == 2

    def test_cleanup_is_idempotent(self, mocker: MagicMock) -> None:
        """Test that cleanup() can be called multiple times safely."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()

        # Call cleanup multiple times
        recorder.cleanup()
        recorder.cleanup()
        recorder.cleanup()

        # Should only terminate once (first call)
        mock_process.terminate.assert_called_once()

    def test_cleanup_handles_already_terminated_process(
        self, mocker: MagicMock
    ) -> None:
        """Test cleanup() when process has already terminated."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # Process already dead
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()
        recorder.cleanup()

        # Should not try to terminate if already dead
        mock_process.terminate.assert_not_called()
        mock_process.kill.assert_not_called()
        assert not recorder._started

    def test_cleanup_before_start(self) -> None:
        """Test that cleanup() does nothing if called before start()."""
        recorder = SinkRecorder("test_monitor.monitor")

        # Should not raise any errors
        recorder.cleanup()

        assert not recorder._started
        assert recorder.process is None

    def test_cleanup_closes_pipes(self, mocker: MagicMock) -> None:
        """Test that cleanup() closes stdout and stderr pipes."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()
        recorder.cleanup()

        mock_stdout.close.assert_called_once()
        mock_stderr.close.assert_called_once()

    def test_cleanup_handles_exception_gracefully(self, mocker: MagicMock) -> None:
        """Test that cleanup() handles exceptions gracefully."""
        mock_popen = mocker.patch("subprocess.Popen")
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.terminate.side_effect = OSError("Process error")
        # Make kill succeed so we can verify fallback
        mock_process.kill.return_value = None
        mock_popen.return_value = mock_process

        recorder = SinkRecorder("test_monitor.monitor")
        recorder.start()

        # Should not raise exception
        recorder.cleanup()

        # Should attempt to kill after terminate fails
        mock_process.kill.assert_called_once()


class TestSinkRecorderIsOpus:
    """Test SinkRecorder is_opus() method."""

    def test_is_opus_returns_false(self) -> None:
        """Test that is_opus() returns False for PCM audio."""
        recorder = SinkRecorder("test_monitor.monitor")

        assert recorder.is_opus() is False


class TestSinkRecorderConstants:
    """Test SinkRecorder class constants."""

    def test_frame_size_constant(self) -> None:
        """Test that FRAME_SIZE is correctly set to 3,840 bytes."""
        assert SinkRecorder.FRAME_SIZE == 3840
