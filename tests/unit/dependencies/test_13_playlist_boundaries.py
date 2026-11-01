"""Regression tests for bounded yt-dlp result iteration."""

from collections.abc import Iterator
from typing import Any

import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.ytdlp import YTDLSource


class GuardedEntries(Iterator[dict[str, Any]]):
    """Yield entries while failing if a consumer crosses the expected boundary."""

    def __init__(self, limit: int) -> None:
        self.consumed = 0
        self._limit = limit

    def __iter__(self) -> GuardedEntries:
        return self

    def __next__(self) -> dict[str, Any]:
        if self.consumed == self._limit:
            raise AssertionError("entries iterator was consumed past its boundary")
        self.consumed += 1
        return {
            "title": f"Track {self.consumed}",
            "webpage_url": f"https://www.youtube.com/watch?v={self.consumed}",
        }


@pytest.mark.asyncio
async def test_playlist_extraction_consumes_at_most_first_100_entries(
    mocker: MockerFixture,
) -> None:
    entries = GuardedEntries(100)
    loop = mocker.Mock()
    loop.run_in_executor = mocker.AsyncMock(
        return_value={"extractor": "youtube:tab", "entries": entries}
    )

    tracks = await YTDLSource.get_tracks_info("playlist-url", loop=loop)

    assert isinstance(tracks, list)
    assert len(tracks) == 100
    assert entries.consumed == 100


@pytest.mark.asyncio
async def test_search_extraction_consumes_at_most_five_entries(
    mocker: MockerFixture,
) -> None:
    entries = GuardedEntries(5)
    loop = mocker.Mock()
    loop.run_in_executor = mocker.AsyncMock(
        return_value={"extractor": "youtube:search", "entries": entries}
    )

    results = await YTDLSource.get_tracks_info("query", loop=loop)

    assert isinstance(results, list)
    assert len(results) == 5
    assert entries.consumed == 5
