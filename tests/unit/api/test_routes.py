"""Tests for API route stubs."""

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from src.api import create_app
from src.shared.models.config import Settings


def test_list_audio_sources_stub(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that list_audio_sources endpoint returns stub response."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/audio-sources")

        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) == 0  # Stub returns empty list


def test_select_audio_source_stub(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that select_audio_source endpoint returns stub response."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/audio-sources/42/select")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["sink_input_id"] == 42


def test_select_audio_source_invalid_id(
    mocker: MockerFixture, test_settings: Settings
) -> None:
    """Test that invalid sink_input_id returns 400 error."""
    # Mock SinkManager
    mock_sink_manager = mocker.Mock()
    mocker.patch("src.api.SinkManager", return_value=mock_sink_manager)

    # Mock Settings to return our test settings
    mocker.patch("src.api.Settings", return_value=test_settings)

    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/audio-sources/-1/select")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data


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
