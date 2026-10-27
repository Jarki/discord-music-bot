"""Regression coverage for stable queue URLs and expiring media streams."""

from io import BytesIO
from typing import Any

import discord
import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.ytdlp import YTDLSource
from src.bot.models import SearchResult, Track

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("webpage_url", ["https://soundcloud.com/artist/song", None])
async def test_track_keeps_stable_url(
    mocker: MockerFixture, webpage_url: str | None
) -> None:
    original_url = "https://soundcloud.com/artist/song?tracking=example"
    mocker.patch(
        "src.bot.dependencies.ytdlp.ytdl.extract_info",
        return_value={
            "extractor": "soundcloud",
            "title": "Song",
            "webpage_url": webpage_url,
            "url": "https://media.example/song?expires=300",
        },
    )

    track = await YTDLSource.get_tracks_info(original_url)

    assert isinstance(track, Track)
    assert track.url == (webpage_url or original_url)


async def test_search_keeps_page_urls_for_selection(mocker: MockerFixture) -> None:
    page_url = "https://www.youtube.com/watch?v=example"
    flat_url = "https://www.youtube.com/watch?v=another"
    mocker.patch(
        "src.bot.dependencies.ytdlp.ytdl.extract_info",
        return_value={
            "extractor": "youtube:search",
            "entries": [
                {
                    "title": "Processed result",
                    "webpage_url": page_url,
                    "url": "https://media.example/song?expires=300",
                },
                {"title": "Flat result", "url": flat_url},
            ],
        },
    )

    results = await YTDLSource.get_tracks_info("example search")

    assert isinstance(results, list)
    assert all(isinstance(result, SearchResult) for result in results)
    assert [result.url for result in results] == [page_url, flat_url]


async def test_delayed_and_repeated_playback_refreshes_expired_streams(
    mocker: MockerFixture,
) -> None:
    page_url = "https://soundcloud.com/artist/song"
    now = 0
    streams: dict[str, int] = {}

    def extract_info(url: str, **kwargs: Any) -> dict[str, Any]:
        if url != page_url:
            raise ValueError("An expiring stream URL cannot be resolved as a track")
        stream_url = f"https://media.example/song?expires={now + 300}"
        streams[stream_url] = now + 300
        return {
            "extractor": "soundcloud",
            "title": "Song",
            "webpage_url": page_url,
            "url": stream_url,
        }

    def open_stream(url: str, **kwargs: Any) -> discord.PCMAudio:
        if streams.get(url, 0) <= now:
            raise PermissionError("403 Forbidden: stream URL expired")
        return discord.PCMAudio(BytesIO(b"\x02\x00" * 1920))

    mocker.patch(
        "src.bot.dependencies.ytdlp.ytdl.extract_info", side_effect=extract_info
    )
    mocker.patch("src.bot.dependencies.ytdlp.discord.FFmpegPCMAudio", open_stream)
    track = await YTDLSource.get_tracks_info(page_url)
    assert isinstance(track, Track)

    # Simulate waiting behind earlier songs, then replaying after another expiry.
    for delay in (600, 600):
        now += delay
        source = await YTDLSource.stream_from_url(track.url)
        try:
            assert source.read() == b"\x01\x00" * 1920
        finally:
            source.cleanup()


async def test_playback_rejects_missing_media_url(mocker: MockerFixture) -> None:
    mocker.patch(
        "src.bot.dependencies.ytdlp.ytdl.extract_info",
        return_value={"webpage_url": "https://soundcloud.com/artist/song"},
    )
    mocker.patch("src.bot.dependencies.ytdlp.discord.FFmpegPCMAudio")

    with pytest.raises(ValueError):
        await YTDLSource.stream_from_url("https://soundcloud.com/artist/song")
