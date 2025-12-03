"""Integration tests for PactlService with real PulseAudio/PipeWire system."""

import shutil
import subprocess

import pytest

from src.api.dependencies.pactl_service import PactlService
from src.api.models.pactl import SinkInput


@pytest.fixture
def pulseaudio_available() -> None:
    """Skip test if pactl is not available on the system."""
    if shutil.which("pactl") is None:
        pytest.skip("pactl command not found - PulseAudio/PipeWire not available")


class TestPactlServiceIntegration:
    """Integration tests for PactlService with real system."""

    def test_get_sink_inputs_from_real_system(self, pulseaudio_available) -> None:
        """Test getting sink-inputs from real PulseAudio/PipeWire system.

        Note: This test will pass with empty results if no audio is playing.
        """
        service = PactlService()
        result = service.get_sink_inputs()

        # Should return a list (may be empty if no audio playing)
        assert isinstance(result, list)

        # If there are results, verify they are valid SinkInput models
        for sink_input in result:
            assert isinstance(sink_input, SinkInput)
            assert isinstance(sink_input.sink_input_id, int)
            assert sink_input.sink_input_id >= 0
            assert isinstance(sink_input.pid, int)
            assert sink_input.pid > 0
            assert isinstance(sink_input.application_name, str)
            assert len(sink_input.application_name) > 0

    def test_sink_inputs_with_no_audio_playing(self, pulseaudio_available) -> None:
        """Test behavior when no audio is playing.

        Note: This test may be unreliable if audio happens to be playing.
        Consider running in a controlled environment or marking as manual.
        """
        service = PactlService()
        result = service.get_sink_inputs()

        # Should return a list (empty if no audio, populated if audio is playing)
        assert isinstance(result, list)

    def test_pids_are_actual_running_processes(self, pulseaudio_available) -> None:
        """Test that PIDs returned correspond to actual running processes."""
        service = PactlService()
        result = service.get_sink_inputs()

        # If there are sink-inputs, verify their PIDs exist
        for sink_input in result:
            # Check if process exists by sending signal 0 (doesn't actually send signal)
            try:
                # On Linux, /proc/<pid> directory exists for running processes
                proc_path = f"/proc/{sink_input.pid}"
                subprocess.run(
                    ["test", "-d", proc_path],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                pytest.fail(
                    f"PID {sink_input.pid} for {sink_input.application_name} "
                    f"does not correspond to a running process"
                )

    def test_application_names_are_valid(self, pulseaudio_available) -> None:
        """Test that application names are non-empty strings."""
        service = PactlService()
        result = service.get_sink_inputs()

        for sink_input in result:
            assert isinstance(sink_input.application_name, str)
            assert len(sink_input.application_name) > 0
            # Application names should not contain only whitespace
            assert sink_input.application_name.strip() == sink_input.application_name

    def test_service_with_custom_timeout(self, pulseaudio_available) -> None:
        """Test that service works with custom timeout."""
        service = PactlService(timeout=10)
        result = service.get_sink_inputs()

        # Should work the same as default timeout
        assert isinstance(result, list)
