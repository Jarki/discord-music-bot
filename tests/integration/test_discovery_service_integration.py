"""Integration tests for DiscoveryService with real system.

These tests interact with the real PulseAudio/PipeWire system and require:
- PulseAudio or PipeWire running
- Hyprland window manager (optional - tests will degrade gracefully)
- Audio applications playing (for some tests)

Tests are designed to be robust and skip if system requirements are not met.
"""

import subprocess

import pytest

from src.api.dependencies.discovery_service import DiscoveryService
from src.api.dependencies.hyprctl_service import HyprctlService
from src.api.dependencies.pactl_service import PactlService
from src.shared.dependencies.virtual_sink import SinkManager
from src.shared.models.config import Settings


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
def discovery_service(test_sink_manager: SinkManager):
    """Create a DiscoveryService with real dependencies."""
    hyprctl_service = HyprctlService()
    pactl_service = PactlService()
    return DiscoveryService(hyprctl_service, pactl_service, test_sink_manager)


class TestDiscoveryServiceIntegration:
    """Integration tests for DiscoveryService with real system."""

    def test_discover_sources_returns_valid_structure(
        self, discovery_service: DiscoveryService
    ):
        """Test that discover_sources returns valid AudioSource models.

        This test should pass even if no audio is playing.
        """
        sources = discovery_service.discover_sources()

        # Should return a list (may be empty if no audio playing)
        assert isinstance(sources, list)

        # If there are sources, verify structure
        for source in sources:
            assert hasattr(source, "sink_input_id")
            assert hasattr(source, "pid")
            assert hasattr(source, "application_name")
            assert hasattr(source, "window_title")
            assert isinstance(source.sink_input_id, int)
            assert isinstance(source.pid, int)
            assert isinstance(source.application_name, str)
            # window_title can be None if no match found
            assert source.window_title is None or isinstance(source.window_title, str)

    def test_discover_sources_with_no_audio_playing(
        self, discovery_service: DiscoveryService
    ):
        """Test discover_sources when no audio is playing.

        Note: This test may fail if audio is actually playing.
        It's informational rather than a hard requirement.
        """
        sources = discovery_service.discover_sources()

        # We can't guarantee no audio is playing, so just verify it's a list
        assert isinstance(sources, list)

    def test_discover_sources_with_hyprctl_unavailable(self, test_sink_manager):
        """Test discover_sources when Hyprland is not running.

        Should still work, but window_title will be None for all sources.
        """
        # Create service with hyprctl that will fail
        hyprctl_service = HyprctlService()
        pactl_service = PactlService()
        discovery_service = DiscoveryService(
            hyprctl_service, pactl_service, test_sink_manager
        )

        # Check if hyprctl is available
        try:
            subprocess.run(
                ["hyprctl", "version"],
                check=True,
                capture_output=True,
                timeout=1,
            )
            pytest.skip("Hyprland is running - test needs it to be unavailable")
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Good - hyprctl not available
            pass

        sources = discovery_service.discover_sources()

        # Should still work, but all window_titles should be None
        assert isinstance(sources, list)
        for source in sources:
            assert source.window_title is None

    @pytest.mark.skip(
        reason="Requires manual setup: audio must be playing to test routing"
    )
    def test_select_source_with_real_audio(self, discovery_service: DiscoveryService):
        """Test routing a real audio source to the virtual sink.

        MANUAL TEST - Requires:
        1. Audio application playing (Firefox, Spotify, etc.)
        2. Run this test manually when audio is playing

        This test is skipped by default as it requires manual setup.
        """
        # Discover sources
        sources = discovery_service.discover_sources()

        # Skip if no audio playing
        if not sources:
            pytest.skip("No audio sources found - need audio playing to test routing")

        # Get the first source
        first_source = sources[0]
        original_sink_input_id = first_source.sink_input_id

        # Route it to our virtual sink
        discovery_service.select_source(original_sink_input_id)

        # Verify routing succeeded (no exception raised)
        # We could verify by checking pactl list sink-inputs,
        # but that would require parsing more output

    def test_select_source_with_invalid_id_raises_error(
        self, discovery_service: DiscoveryService
    ):
        """Test that selecting an invalid sink_input_id raises an error."""
        # Use a very high ID that's unlikely to exist
        invalid_id = 999999

        with pytest.raises(RuntimeError):
            discovery_service.select_source(invalid_id)

    def test_integration_with_pactl_service(self, test_sink_manager: SinkManager):
        """Test integration between DiscoveryService and PactlService."""
        hyprctl_service = HyprctlService()
        pactl_service = PactlService()
        discovery_service = DiscoveryService(
            hyprctl_service, pactl_service, test_sink_manager
        )

        # Get sources via discovery service
        sources = discovery_service.discover_sources()

        # Get sink-inputs directly from pactl service
        sink_inputs = pactl_service.get_sink_inputs()

        # Should have same number of sources as sink-inputs
        assert len(sources) == len(sink_inputs)

        # Verify that each source corresponds to a sink-input
        source_ids = {s.sink_input_id for s in sources}
        sink_input_ids = {si.sink_input_id for si in sink_inputs}
        assert source_ids == sink_input_ids

    def test_integration_with_hyprctl_service(self, test_sink_manager: SinkManager):
        """Test integration between DiscoveryService and HyprctlService.

        This test will pass even if Hyprland is not running.
        """
        hyprctl_service = HyprctlService()
        pactl_service = PactlService()
        discovery_service = DiscoveryService(
            hyprctl_service, pactl_service, test_sink_manager
        )

        sources = discovery_service.discover_sources()

        # Try to get clients directly from hyprctl
        try:
            clients = hyprctl_service.get_clients()
            client_pids = {c.pid for c in clients}

            # If hyprctl works, verify that sources with window_titles
            # have PIDs that exist in hyprctl output
            for source in sources:
                if source.window_title is not None:
                    assert source.pid in client_pids

        except (RuntimeError, FileNotFoundError):
            # Hyprland not running - all window_titles should be None
            for source in sources:
                assert source.window_title is None

    def test_discover_sources_multiple_calls(self, discovery_service: DiscoveryService):
        """Test that discover_sources can be called multiple times."""
        # Call multiple times
        sources1 = discovery_service.discover_sources()
        sources2 = discovery_service.discover_sources()
        sources3 = discovery_service.discover_sources()

        # All should succeed and return lists
        assert isinstance(sources1, list)
        assert isinstance(sources2, list)
        assert isinstance(sources3, list)

        # Results may differ if audio state changes, but structure should be same
