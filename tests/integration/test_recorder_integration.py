"""Integration tests for SinkRecorder.

These tests interact with the actual PulseAudio/PipeWire system to verify
real-world behavior of the audio recorder.

Requirements:
- PulseAudio or PipeWire must be installed and running
- `pactl` and `parec` commands must be available
- Tests will create and destroy real null sinks
- Tests may capture ambient system audio (no audio content verification)
"""

import contextlib
import subprocess
import time
from collections.abc import Generator

import pytest

from src.bot.dependencies.recorder import SinkRecorder
from src.shared.dependencies.virtual_sink import SinkManager
from src.shared.models.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Get test settings with unique sink name.

    Returns:
        Settings instance configured for testing
    """
    return Settings(
        sink_name="test_recorder_sink",
        discord_token="test_token_not_used",
    )


@pytest.fixture
def test_sink_with_monitor(
    test_settings: Settings, pulseaudio_available: bool
) -> Generator[str]:
    """Create a real virtual sink with monitor source for testing.

    This fixture creates an actual null sink in the audio system and
    provides the monitor source name for testing. The sink is cleaned
    up after the test completes.

    Args:
        test_settings: Settings instance with unique sink name
        pulseaudio_available: Ensures PulseAudio is available

    Yields:
        Monitor source name (e.g., "test_recorder_sink.monitor")

    Note:
        This fixture creates a real audio sink in the system. Tests
        should not assume any audio is playing through it.
    """
    manager = SinkManager(
        sink_name=test_settings.sink_name,
        sample_rate=test_settings.audio_rate,
        channels=test_settings.audio_channels,
    )

    try:
        # Create the sink
        manager.create()

        # Wait a moment for the sink to be fully initialized
        time.sleep(0.1)

        # Verify the monitor source exists
        result = subprocess.run(
            ["pactl", "list", "short", "sources"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        monitor_name = f"{test_settings.sink_name}.monitor"
        if monitor_name not in result.stdout:
            pytest.fail(f"Monitor source {monitor_name} not found after sink creation")

        yield monitor_name

    finally:
        # Cleanup
        with contextlib.suppress(Exception):
            manager.destroy()


@pytest.fixture
def parec_available() -> bool:
    """Check if parec command is available on the system.

    Returns:
        True if parec is available

    Raises:
        pytest.skip: If parec is not available
    """
    try:
        subprocess.run(
            ["parec", "--version"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        return True
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        pytest.skip("parec command not available on this system")


@pytest.mark.integration
class TestSinkRecorderIntegration:
    """Integration tests for SinkRecorder with real audio system."""

    def test_recorder_can_start_with_real_monitor_source(
        self, test_sink_with_monitor: str, parec_available: bool
    ) -> None:
        """Test that recorder can start with a real monitor source."""
        recorder = SinkRecorder(test_sink_with_monitor)

        try:
            recorder.start()

            # Verify process is running
            assert recorder._started
            assert recorder.process is not None
            assert recorder.process.poll() is None  # None means still running

        finally:
            recorder.cleanup()

    def test_recorder_reads_real_audio_data(
        self, test_sink_with_monitor: str, parec_available: bool
    ) -> None:
        """Test that recorder can read audio data from real monitor source.

        Note:
            This test verifies the mechanism works, not audio content.
            The data may be silence if no audio is playing.
        """
        recorder = SinkRecorder(test_sink_with_monitor)

        try:
            recorder.start()

            # Read multiple frames
            data1 = recorder.read()
            data2 = recorder.read()
            data3 = recorder.read()

            # Verify correct frame size
            assert len(data1) == 3840
            assert len(data2) == 3840
            assert len(data3) == 3840

            # Verify we got some data (even if it's silence)
            assert isinstance(data1, bytes)
            assert isinstance(data2, bytes)
            assert isinstance(data3, bytes)

        finally:
            recorder.cleanup()

    def test_recorder_cleanup_terminates_subprocess(
        self, test_sink_with_monitor: str, parec_available: bool
    ) -> None:
        """Test that cleanup terminates the parec subprocess."""
        recorder = SinkRecorder(test_sink_with_monitor)

        try:
            recorder.start()

            # Get process info
            assert recorder.process is not None
            pid = recorder.process.pid

            # Cleanup
            recorder.cleanup()

            # Wait a moment for process to terminate
            time.sleep(0.1)

            # Verify process no longer exists
            try:
                # Try to check if process exists (will raise if it doesn't)
                result = subprocess.run(
                    ["ps", "-p", str(pid)],
                    capture_output=True,
                    timeout=5,
                )
                # If ps returns 0, process still exists (bad)
                # If ps returns non-zero, process doesn't exist (good)
                assert result.returncode != 0, (
                    f"Process {pid} still exists after cleanup"
                )
            except subprocess.TimeoutExpired:
                pytest.fail("Timeout checking if process terminated")

        finally:
            # Ensure cleanup even if test fails
            with contextlib.suppress(Exception):
                recorder.cleanup()

    def test_recorder_with_nonexistent_monitor_source(
        self, parec_available: bool
    ) -> None:
        """Test that recorder handles non-existent monitor source appropriately.

        Note:
            parec doesn't immediately fail with a non-existent source - it starts
            successfully and produces silence (zeros). This test verifies that the
            recorder doesn't crash and produces data (even if it's all zeros).
        """
        recorder = SinkRecorder("nonexistent_monitor.monitor")

        try:
            # Start should succeed (parec doesn't validate source immediately)
            recorder.start()

            # Should be able to read data (likely all zeros/silence)
            data = recorder.read()

            # Should get data (even if it's silence)
            assert len(data) == 3840, (
                "Should still produce frames even from non-existent source"
            )

        except (subprocess.SubprocessError, FileNotFoundError):
            # It's also acceptable for start() to raise an error
            pass

        finally:
            recorder.cleanup()

    def test_multiple_read_cycles(
        self, test_sink_with_monitor: str, parec_available: bool
    ) -> None:
        """Test reading many frames to verify consistent behavior.

        This test reads 100 frames (about 2 seconds of audio) to verify
        that the recorder maintains consistent frame sizes and doesn't
        degrade over time.
        """
        recorder = SinkRecorder(test_sink_with_monitor)

        try:
            recorder.start()

            # Read 100 frames (2 seconds at 20ms per frame)
            frame_count = 100
            frames_read = 0
            incorrect_sizes = 0

            for _ in range(frame_count):
                data = recorder.read()

                if len(data) == 3840:
                    frames_read += 1
                elif len(data) == 0:
                    # Empty read - might indicate end of stream or error
                    break
                else:
                    incorrect_sizes += 1

            # Should successfully read most frames with correct size
            assert frames_read >= 95, (
                f"Only read {frames_read}/{frame_count} frames correctly"
            )
            assert incorrect_sizes == 0, (
                f"Got {incorrect_sizes} frames with incorrect size"
            )

        finally:
            recorder.cleanup()

    def test_recorder_cleanup_is_idempotent_integration(
        self, test_sink_with_monitor: str, parec_available: bool
    ) -> None:
        """Test that cleanup can be called multiple times safely."""
        recorder = SinkRecorder(test_sink_with_monitor)

        recorder.start()
        started_before = recorder._started
        assert started_before is True

        # Call cleanup multiple times - all should succeed without error
        recorder.cleanup()
        started_after = recorder._started
        assert started_after is False

        # These should not raise even though already cleaned up
        recorder.cleanup()
        recorder.cleanup()

    def test_recorder_with_custom_audio_parameters(
        self, test_sink_with_monitor: str, parec_available: bool
    ) -> None:
        """Test recorder with different audio parameters.

        Note:
            This test uses default 48kHz stereo since our test sink
            is created with those defaults. It verifies the parameters
            are correctly passed to parec.
        """
        recorder = SinkRecorder(
            monitor_source=test_sink_with_monitor,
            audio_format="s16le",
            audio_rate=48000,
            audio_channels=2,
        )

        try:
            recorder.start()

            # Read some data to verify it works
            data = recorder.read()

            assert len(data) == 3840  # Should still be correct frame size

        finally:
            recorder.cleanup()

    def test_recorder_read_before_start(self) -> None:
        """Test that reading before starting returns empty bytes."""
        recorder = SinkRecorder("test_monitor.monitor")

        # Don't start, just try to read
        data = recorder.read()

        assert data == b""
        assert not recorder._started

    def test_recorder_is_opus_integration(self, test_sink_with_monitor: str) -> None:
        """Test that is_opus returns False for integration test."""
        recorder = SinkRecorder(test_sink_with_monitor)

        assert recorder.is_opus() is False

        # Should still be False after starting
        try:
            recorder.start()
            assert recorder.is_opus() is False
        finally:
            recorder.cleanup()
