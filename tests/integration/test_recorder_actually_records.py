"""Integration tests for SinkRecorder.

These tests interact with the actual PulseAudio/PipeWire system to verify
real-world behavior of the audio recorder.

Requirements:
- PulseAudio or PipeWire must be installed and running
- `pactl` and `parec` commands must be available
- Tests will create and destroy real null sinks
- Tests may capture ambient system audio (no audio content verification)
"""

import pathlib
import subprocess
import time
from collections.abc import Generator

import pytest

from src.api.dependencies.discovery_service import (
    DiscoveryService,
    HyprctlService,
    PactlService,
)
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
def test_sink_manager(test_settings: Settings):
    """Create a temporary sink manager for testing."""
    sink_manager = SinkManager(
        sink_name=f"{test_settings.sink_name}_integration_test",
        sample_rate=test_settings.audio_rate,
        channels=test_settings.audio_channels,
    )
    try:
        sink_manager.create()
        yield sink_manager
    finally:
        sink_manager.destroy()


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


@pytest.fixture
def test_audio_file() -> str:
    assets_dir = pathlib.Path(__file__).parent / "assets" / "audio"
    return str(assets_dir / "bruh_sound_effect.wav")


@pytest.fixture
def discovery_service(test_sink_manager: SinkManager) -> DiscoveryService:
    """Create a DiscoveryService with real dependencies."""
    hyprctl_service = HyprctlService()
    pactl_service = PactlService()
    return DiscoveryService(hyprctl_service, pactl_service, test_sink_manager)


@pytest.fixture
def paplay_available() -> bool:
    """Check if paplay command is available on the system.

    Returns:
        True if paplay is available

    Raises:
        pytest.skip: If paplay is not available
    """
    try:
        subprocess.run(
            ["paplay", "--version"],
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
        pytest.skip("paplay command not available on this system")


@pytest.fixture
def test_sink_fully_connected(
    test_sink_manager: SinkManager,
    discovery_service: DiscoveryService,
    test_audio_file: str,
    paplay_available: bool,
) -> Generator[str]:
    """Ensure the test sink is created and has audio routed to it.

    Yields:
        The monitor source name of the test sink
    """
    monitor_source = test_sink_manager.get_monitor_source()

    audio_sources = discovery_service.discover_sources()
    paplay_sources = [src for src in audio_sources if "paplay" in src.application_name]
    if len(paplay_sources) > 1:
        raise RuntimeError(
            "Multiple paplay sources detected. Please close other audio players "
            "before running this test."
        )
    # run the input
    proc = subprocess.Popen(["paplay", test_audio_file])
    try:
        start_time = time.time()
        timeout = 5.0  # seconds
        paplay_source = None
        while time.time() - start_time < timeout:
            # Find the paplay source
            audio_sources = discovery_service.discover_sources()
            try:
                paplay_source = next(
                    src for src in audio_sources if "paplay" in src.application_name
                )
                break
            except StopIteration:
                paplay_source = None

            time.sleep(0.001)
        else:
            raise RuntimeError("Timed out waiting for paplay source to appear.")

        discovery_service.select_source(paplay_source.sink_input_id)
        yield monitor_source
    finally:
        proc.terminate()
        proc.wait()


@pytest.mark.produces_files
class TestSinkRecorderIntegration:
    """Integration tests for SinkRecorder with real audio system."""

    @pytest.mark.slow
    def test_recorder_reads_real_audio_data(
        self, parec_available: bool, test_sink_fully_connected: str
    ) -> None:
        """Test that recorder can without mistake read audio data from the monitor source."""
        recorder = SinkRecorder(test_sink_fully_connected)

        output_file = pathlib.Path("test_output.raw")

        try:
            recorder.start()

            # Attempt to read multiple frames
            frames_to_read = 50 * 3  # Read for 3 seconds
            with output_file.open("wb") as f:  # Changed to "wb" to overwrite
                for _ in range(frames_to_read):
                    data = recorder.read()
                    f.write(data)

            print(f"Recorded audio data written to {output_file}")
            print(
                f"You can play it back with: paplay --raw --rate=48000 --channels=2 {output_file}"
            )

        finally:
            recorder.cleanup()
