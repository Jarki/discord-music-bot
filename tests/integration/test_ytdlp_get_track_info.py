import pytest

from src.bot.dependencies.ytdlp import YTDLSource
from src.bot.models import SearchResult, Track


@pytest.fixture(scope="function")
def test_url_one_track() -> str:
    """Fixture to provide a test URL for YTDLSource tests."""
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture(scope="function")
def test_url_playlist() -> str:
    """Fixture to provide a test playlist URL for YTDLSource tests."""
    return "https://www.youtube.com/watch?v=Qtogm_mo1AQ&list=PLMmqTuUsDkRIZ1C1T2AsVz5XIxtVDfSOe"


@pytest.fixture(scope="function")
def test_search() -> str:
    """Fixture to provide a test search query for YTDLSource tests."""
    return "Never Gonna Give You Up"


@pytest.mark.integration
@pytest.mark.skip(reason="Enable if testing manually")
async def test_get_track_info_integration(test_url_one_track: str) -> None:
    track = await YTDLSource.get_tracks_info(test_url_one_track)

    assert isinstance(track, list)
    assert all(isinstance(t, Track) for t in track)
    assert all(isinstance(t.title, str) and t.title for t in track)
    assert all(isinstance(t.url, str) and t.url for t in track)
    assert all(isinstance(t.duration, int) and t.duration >= 0 for t in track)


@pytest.mark.integration
@pytest.mark.skip(reason="Enable if testing manually")
async def test_get_track_info_search(test_search: str):
    search_results = await YTDLSource.get_tracks_info(test_search)

    assert isinstance(search_results, list)
    assert all(isinstance(t, SearchResult) for t in search_results)
