"""Unit tests for bot utilities."""


from src.bot.models import Track
from src.bot.utils import tracks_to_pages


class TestTracksToPages:
    """Test tracks_to_pages function."""

    def test_tracks_to_pages_basic(self) -> None:
        """Test basic pagination of tracks."""
        tracks = [
            Track(type="youtube", title="Song 1", url="https://example.com/1"),
            Track(type="youtube", title="Song 2", url="https://example.com/2"),
            Track(type="youtube", title="Song 3", url="https://example.com/3"),
        ]

        pages = tracks_to_pages(tracks, songs_per_page=2)

        assert len(pages) == 2
        assert pages[0] == "1: Song 1\n2: Song 2"
        assert pages[1] == "3: Song 3"
