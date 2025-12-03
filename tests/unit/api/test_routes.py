"""Tests for API route stubs."""

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from src.api import create_app
from src.api.dependencies import get_discovery_service
from src.api.models.audio_source import AudioSource
from src.shared.models.config import Settings


def test_list_audio_sources_returns_sources(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that list_audio_sources endpoint returns discovered sources."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    # Mock DiscoveryService.discover_sources
    mock_audio_sources = [
        AudioSource(
            sink_input_id=42,
            pid=1234,
            application_name="Firefox",
            window_title="YouTube - Video Title",
        ),
        AudioSource(
            sink_input_id=43,
            pid=5678,
            application_name="Spotify",
            window_title="Spotify Premium",
        ),
    ]
    mock_discovery_service = mocker.Mock()
    mock_discovery_service.discover_sources.return_value = mock_audio_sources

    app = create_app()

    # Override the dependency
    app.dependency_overrides[get_discovery_service] = lambda: mock_discovery_service

    with TestClient(app) as client:
        response = client.get("/api/audio-sources")

        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert len(data["sources"]) == 2
        assert data["sources"][0]["sink_input_id"] == 42
        assert data["sources"][0]["application_name"] == "Firefox"
        assert data["sources"][1]["sink_input_id"] == 43


def test_list_audio_sources_handles_discovery_error(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that list_audio_sources handles discovery service errors."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    # Mock DiscoveryService.discover_sources to raise error
    mock_discovery_service = mocker.Mock()
    mock_discovery_service.discover_sources.side_effect = RuntimeError(
        "Failed to get sink-inputs"
    )

    app = create_app()

    # Override the dependency
    app.dependency_overrides[get_discovery_service] = lambda: mock_discovery_service

    with TestClient(app) as client:
        response = client.get("/api/audio-sources")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Failed to get sink-inputs" in data["detail"]


def test_list_audio_sources_empty_results(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that list_audio_sources returns empty list when no sources."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    # Mock DiscoveryService.discover_sources to return empty list
    mock_discovery_service = mocker.Mock()
    mock_discovery_service.discover_sources.return_value = []

    app = create_app()

    # Override the dependency
    app.dependency_overrides[get_discovery_service] = lambda: mock_discovery_service

    with TestClient(app) as client:
        response = client.get("/api/audio-sources")

        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert len(data["sources"]) == 0


def test_select_audio_source_success(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that select_audio_source successfully routes audio."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    # Mock DiscoveryService.select_source
    mock_discovery_service = mocker.Mock()

    app = create_app()

    # Override the dependency
    app.dependency_overrides[get_discovery_service] = lambda: mock_discovery_service

    with TestClient(app) as client:
        response = client.post("/api/audio-sources/42/select")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["sink_input_id"] == 42
        assert "routed to virtual sink" in data["message"]

        mock_discovery_service.select_source.assert_called_once_with(42)


def test_select_audio_source_invalid_id(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that invalid sink_input_id returns 400 error."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    # Mock DiscoveryService
    mock_discovery_service = mocker.Mock()

    app = create_app()

    # Override the dependency
    app.dependency_overrides[get_discovery_service] = lambda: mock_discovery_service

    with TestClient(app) as client:
        response = client.post("/api/audio-sources/-1/select")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Invalid sink_input_id" in data["detail"]

        # Should not call select_source for invalid ID
        mock_discovery_service.select_source.assert_not_called()


def test_select_audio_source_routing_failure(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that routing failure returns 404 error."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    # Mock DiscoveryService.select_source to raise error
    mock_discovery_service = mocker.Mock()
    mock_discovery_service.select_source.side_effect = RuntimeError(
        "Failed to route sink input"
    )

    app = create_app()

    # Override the dependency
    app.dependency_overrides[get_discovery_service] = lambda: mock_discovery_service

    with TestClient(app) as client:
        response = client.post("/api/audio-sources/42/select")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "Failed to route sink input" in data["detail"]


def test_health_check_returns_healthy(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that health check endpoint returns healthy status."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "loud-bot-api"
