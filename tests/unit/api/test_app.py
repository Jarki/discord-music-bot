"""Tests for FastAPI app factory and configuration."""

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from src.api import create_app
from src.shared.models.config import Settings


def test_create_app(mocker: MockerFixture, test_settings: Settings) -> None:
    """Test that create_app returns a FastAPI instance."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    app = create_app()

    assert app.title == "LOUD Bot API"
    assert app.version == "0.1.0"


def test_app_lifespan_creates_sink(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that app lifespan creates sink on startup."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    app = create_app()

    # TestClient triggers lifespan events
    with TestClient(app) as client:
        # Verify sink was created during startup
        mock_sink_manager.create.assert_called_once()

        # Verify sink_manager stored in app state
        assert hasattr(client.app.state, "sink_manager")  # type: ignore[attr-defined]


def test_app_lifespan_destroys_sink(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that app lifespan destroys sink on shutdown."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    app = create_app()

    with TestClient(app):
        pass  # Context exit triggers shutdown

    # Verify sink was destroyed during shutdown
    mock_sink_manager.destroy.assert_called_once()


def test_health_endpoint(mocker: MockerFixture, test_settings: Settings) -> None:
    """Test that health check endpoint works."""
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


def test_sink_manager_called_with_settings(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that SinkManager is initialized with values from settings."""
    # Mock SinkManager
    mock_sink_manager_class = mocker.patch("src.api.SinkManager")
    mock_sink_manager = mocker.Mock()
    mock_sink_manager_class.return_value = mock_sink_manager

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    app = create_app()

    with TestClient(app):
        # Verify SinkManager was initialized with correct settings
        mock_sink_manager_class.assert_called_once_with(
            sink_name=test_settings.sink_name,
            sample_rate=test_settings.audio_rate,
            channels=test_settings.audio_channels,
        )
