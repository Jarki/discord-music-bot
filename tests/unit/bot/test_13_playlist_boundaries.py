"""Regression tests for playlist command index and result boundaries."""

import inspect
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from src.bot.client import Music
from src.bot.models.core import PlaylistTrack, Track


def make_context(mocker: MockerFixture) -> SimpleNamespace:
    return SimpleNamespace(
        interaction=SimpleNamespace(
            response=SimpleNamespace(defer=mocker.AsyncMock()),
            followup=SimpleNamespace(send=mocker.AsyncMock()),
            edit_original_response=mocker.AsyncMock(),
        ),
        text_channel=SimpleNamespace(send=mocker.AsyncMock()),
        author=mocker.Mock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested_index", "expected_positions"),
    [(1, range(1, 101)), (100, range(100, 101))],
)
async def test_play_starts_within_retained_first_100_entries(
    mocker: MockerFixture,
    requested_index: int,
    expected_positions: range,
) -> None:
    playlist = [
        PlaylistTrack(yt_url=f"https://youtube.example/watch?v={position}")
        for position in range(1, 151)
    ]
    mocker.patch(
        "src.bot.client.YTDLSource.get_tracks_info", return_value=playlist
    )
    resolve = mocker.patch.object(
        Music,
        "try_handle_get_track_info_from_yt_url",
        return_value=Track(type="youtube", title="Track", url="track-url"),
    )
    mocker.patch.object(Music, "_queue_track_and_play_maybe", return_value=None)
    context = make_context(mocker)

    await inspect.unwrap(Music.play.callback)(
        Music(mocker.Mock()),
        context,
        f"https://youtube.example/playlist?list=example&index={requested_index}",
    )

    assert [call.args[2] for call in resolve.await_args_list] == list(
        expected_positions
    )
    assert all(call.args[3] == 100 for call in resolve.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_index", [0, -1, 101])
async def test_play_rejects_index_outside_retained_first_100_entries(
    mocker: MockerFixture, requested_index: int
) -> None:
    playlist = [
        PlaylistTrack(yt_url=f"https://youtube.example/watch?v={position}")
        for position in range(1, 151)
    ]
    mocker.patch(
        "src.bot.client.YTDLSource.get_tracks_info", return_value=playlist
    )
    resolve = mocker.patch.object(
        Music, "try_handle_get_track_info_from_yt_url"
    )
    context = make_context(mocker)

    await inspect.unwrap(Music.play.callback)(
        Music(mocker.Mock()),
        context,
        f"https://youtube.example/playlist?list=example&index={requested_index}",
    )

    resolve.assert_not_awaited()
    context.interaction.followup.send.assert_awaited_once_with(
        content="Playlist index must be between 1 and 100."
    )


@pytest.mark.asyncio
async def test_play_reports_empty_playlist(mocker: MockerFixture) -> None:
    mocker.patch("src.bot.client.YTDLSource.get_tracks_info", return_value=[])
    context = make_context(mocker)

    await inspect.unwrap(Music.play.callback)(
        Music(mocker.Mock()), context, "https://youtube.example/playlist?list=empty"
    )

    context.interaction.followup.send.assert_awaited_once_with(
        content="No tracks found in the playlist."
    )
    context.interaction.edit_original_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_play_does_not_claim_success_when_every_playlist_entry_fails(
    mocker: MockerFixture,
) -> None:
    playlist = [PlaylistTrack(yt_url="https://youtube.example/watch?v=missing")]
    mocker.patch(
        "src.bot.client.YTDLSource.get_tracks_info", return_value=playlist
    )
    mocker.patch.object(
        Music, "try_handle_get_track_info_from_yt_url", return_value=None
    )
    context = make_context(mocker)

    await inspect.unwrap(Music.play.callback)(
        Music(mocker.Mock()), context, "https://youtube.example/playlist?list=failed"
    )

    context.interaction.edit_original_response.assert_awaited_once_with(
        content="No tracks from the playlist were added."
    )


@pytest.mark.asyncio
async def test_malformed_playlist_index_keeps_first_track_fallback(
    mocker: MockerFixture,
) -> None:
    playlist = [PlaylistTrack(yt_url="https://youtube.example/watch?v=first")]
    mocker.patch(
        "src.bot.client.YTDLSource.get_tracks_info", return_value=playlist
    )
    resolve = mocker.patch.object(
        Music, "try_handle_get_track_info_from_yt_url", return_value=None
    )
    context = make_context(mocker)

    await inspect.unwrap(Music.play.callback)(
        Music(mocker.Mock()),
        context,
        "https://youtube.example/playlist?list=example&index=not-a-number",
    )

    assert resolve.await_args.args[2:] == (1, 1)
