"""Unit tests for DiscoveryService."""

import pytest

from src.api.dependencies.discovery_service import DiscoveryService
from src.api.models.hyprctl import HyprlandClient
from src.api.models.pactl import SinkInput


class TestDiscoverSources:
    """Tests for DiscoveryService.discover_sources()."""

    def test_discover_sources_with_matching_pids(self, mocker):
        """Test discover_sources matches sink-inputs with window titles by PID."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        # Mock hyprctl to return clients
        mock_hyprctl.get_clients.return_value = [
            HyprlandClient(pid=1234, title="Firefox - YouTube"),
            HyprlandClient(pid=5678, title="Spotify Premium"),
        ]

        # Mock pactl to return sink-inputs
        mock_pactl.get_sink_inputs.return_value = [
            SinkInput(sink_input_id=42, pid=1234, application_name="Firefox"),
            SinkInput(sink_input_id=43, pid=5678, application_name="Spotify"),
        ]

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act
        sources = service.discover_sources()

        # Assert
        assert len(sources) == 2

        assert sources[0].sink_input_id == 42
        assert sources[0].pid == 1234
        assert sources[0].application_name == "Firefox"
        assert sources[0].window_title == "Firefox - YouTube"

        assert sources[1].sink_input_id == 43
        assert sources[1].pid == 5678
        assert sources[1].application_name == "Spotify"
        assert sources[1].window_title == "Spotify Premium"

        mock_hyprctl.get_clients.assert_called_once()
        mock_pactl.get_sink_inputs.assert_called_once()

    def test_discover_sources_with_unmatched_pids(self, mocker):
        """Test discover_sources sets window_title to None when PID not in hyprctl."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        # Mock hyprctl to return clients with different PIDs
        mock_hyprctl.get_clients.return_value = [
            HyprlandClient(pid=9999, title="Some Other Window"),
        ]

        # Mock pactl to return sink-input with no matching PID
        mock_pactl.get_sink_inputs.return_value = [
            SinkInput(sink_input_id=42, pid=1234, application_name="Firefox"),
        ]

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act
        sources = service.discover_sources()

        # Assert
        assert len(sources) == 1
        assert sources[0].sink_input_id == 42
        assert sources[0].pid == 1234
        assert sources[0].application_name == "Firefox"
        assert sources[0].window_title is None

    def test_discover_sources_when_hyprctl_fails(self, mocker):
        """Test discover_sources continues with None window_titles when hyprctl fails."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        # Mock hyprctl to raise exception
        mock_hyprctl.get_clients.side_effect = RuntimeError("hyprctl failed")

        # Mock pactl to return sink-inputs
        mock_pactl.get_sink_inputs.return_value = [
            SinkInput(sink_input_id=42, pid=1234, application_name="Firefox"),
        ]

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act
        sources = service.discover_sources()

        # Assert - should continue with None window_title
        assert len(sources) == 1
        assert sources[0].sink_input_id == 42
        assert sources[0].pid == 1234
        assert sources[0].application_name == "Firefox"
        assert sources[0].window_title is None

        mock_hyprctl.get_clients.assert_called_once()
        mock_pactl.get_sink_inputs.assert_called_once()

    def test_discover_sources_when_pactl_fails(self, mocker):
        """Test discover_sources raises exception when pactl fails."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        # Mock pactl to raise exception
        mock_pactl.get_sink_inputs.side_effect = RuntimeError("pactl failed")

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act & Assert - should raise exception
        with pytest.raises(RuntimeError, match="Failed to get sink-inputs from pactl"):
            service.discover_sources()

        mock_pactl.get_sink_inputs.assert_called_once()
        # hyprctl should not be called if pactl fails first
        # (though in current implementation it may be called after)

    def test_discover_sources_with_empty_results(self, mocker):
        """Test discover_sources returns empty list when no audio sources."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        # Mock both services to return empty lists
        mock_hyprctl.get_clients.return_value = []
        mock_pactl.get_sink_inputs.return_value = []

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act
        sources = service.discover_sources()

        # Assert
        assert len(sources) == 0
        mock_hyprctl.get_clients.assert_called_once()
        mock_pactl.get_sink_inputs.assert_called_once()

    def test_discover_sources_with_partial_matches(self, mocker):
        """Test discover_sources handles mix of matched and unmatched PIDs."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        # Mock hyprctl with one matching PID
        mock_hyprctl.get_clients.return_value = [
            HyprlandClient(pid=1234, title="Firefox - YouTube"),
        ]

        # Mock pactl with two sink-inputs, one matching, one not
        mock_pactl.get_sink_inputs.return_value = [
            SinkInput(sink_input_id=42, pid=1234, application_name="Firefox"),
            SinkInput(sink_input_id=43, pid=5678, application_name="Spotify"),
        ]

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act
        sources = service.discover_sources()

        # Assert
        assert len(sources) == 2
        assert sources[0].window_title == "Firefox - YouTube"
        assert sources[1].window_title is None


class TestSelectSource:
    """Tests for DiscoveryService.select_source()."""

    def test_select_source_success(self, mocker):
        """Test select_source calls sink_manager.route_sink_input correctly."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act
        service.select_source(42)

        # Assert
        mock_sink_manager.route_sink_input.assert_called_once_with(sink_input_id=42)

    def test_select_source_failure(self, mocker):
        """Test select_source propagates exception when routing fails."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        # Mock routing to raise exception
        mock_sink_manager.route_sink_input.side_effect = RuntimeError(
            "Failed to route sink input"
        )

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to route sink input"):
            service.select_source(42)

        mock_sink_manager.route_sink_input.assert_called_once_with(sink_input_id=42)

    def test_select_source_with_different_ids(self, mocker):
        """Test select_source works with various sink_input_ids."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Act - test with different IDs
        service.select_source(0)
        service.select_source(100)
        service.select_source(999)

        # Assert
        assert mock_sink_manager.route_sink_input.call_count == 3
        mock_sink_manager.route_sink_input.assert_any_call(sink_input_id=0)
        mock_sink_manager.route_sink_input.assert_any_call(sink_input_id=100)
        mock_sink_manager.route_sink_input.assert_any_call(sink_input_id=999)


class TestDiscoveryServiceInit:
    """Tests for DiscoveryService initialization."""

    def test_init_stores_dependencies(self, mocker):
        """Test DiscoveryService stores all dependencies correctly."""
        # Arrange
        mock_hyprctl = mocker.Mock()
        mock_pactl = mocker.Mock()
        mock_sink_manager = mocker.Mock()

        # Act
        service = DiscoveryService(mock_hyprctl, mock_pactl, mock_sink_manager)

        # Assert
        assert service.hyprctl_service is mock_hyprctl
        assert service.pactl_service is mock_pactl
        assert service.sink_manager is mock_sink_manager
