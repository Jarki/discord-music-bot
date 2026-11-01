"""Playlist command boundary regressions."""

import inspect
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from src.bot.client import Music
from src.bot.models.core import PlaylistTrack, Track


@pytest.mark.asyncio
@pytest.mark.parametrize("playlist_size", [99, 100, 101, 150])
async def test_play_queues_only_first_100_playlist_entries(
    mocker: MockerFixture, playlist_size: int
) -> None:
    playlist = [
        PlaylistTrack(yt_url=f"https://www.youtube.com/watch?v=track{i}")
        for i in range(playlist_size)
    ]
    tracks = [
        Track(type="youtube", title=f"Track {i}", url=entry.yt_url)
        for i, entry in enumerate(playlist)
    ]
    extract = mocker.patch(
        "src.bot.client.YTDLSource.get_tracks_info",
        side_effect=[playlist, *tracks],
    )
    queue_track = mocker.patch.object(
        Music, "_queue_track_and_play_maybe", return_value=None
    )
    context = SimpleNamespace(
        interaction=SimpleNamespace(
            response=SimpleNamespace(
                defer=mocker.AsyncMock(), is_done=lambda: False
            ),
            followup=SimpleNamespace(send=mocker.AsyncMock()),
            edit_original_response=mocker.AsyncMock(),
        )
    )
    music = Music(mocker.Mock())

    await inspect.unwrap(Music.play.callback)(
        music, context, "https://www.youtube.com/playlist?list=example"
    )

    expected = tracks[:100]
    assert queue_track.await_args_list == [
        mocker.call(context, track) for track in expected
    ]
    assert [call.args[0] for call in extract.await_args_list[1:]] == [
        track.url for track in expected
    ]
