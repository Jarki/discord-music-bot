"""Regressions for skip playback ownership and current-track metadata."""

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_mock import MockerFixture

from src.bot.client import Music
from src.bot.dependencies.player import Player
from src.bot.dependencies.queue.in_memory import InMemoryQueueManager
from src.bot.models.core import Track

pytestmark = pytest.mark.asyncio


def _track(name: str) -> Track:
    return Track(type="youtube", title=name, url=f"https://example.com/{name}")


def _player(
    mocker: MockerFixture, tracks: list[Track]
) -> tuple[Player, InMemoryQueueManager, Any]:
    queue = InMemoryQueueManager()
    for track in tracks:
        queue.queue_item("1", track)

    voice = mocker.Mock()
    voice.is_playing.return_value = False
    voice.is_paused.return_value = False
    voice.is_connected.return_value = True
    bot = mocker.Mock()
    bot.loop = asyncio.get_running_loop()
    player = Player("1", queue, bot)
    mocker.patch.object(player, "_get_voice_client", return_value=voice)
    return player, queue, voice


async def test_skip_starts_and_reports_successor_as_current(
    mocker: MockerFixture,
) -> None:
    first, second, third = (_track(name) for name in ("A", "B", "C"))
    player, _, voice = _player(mocker, [first, second, third])
    first_source, second_source = mocker.Mock(), mocker.Mock()
    stream = mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        side_effect=[first_source, second_source],
    )

    assert await player.play_next() is first
    voice.is_playing.return_value = True

    skipped, started = await player.skip_tracks(1)

    assert skipped == 1
    assert started is second
    assert player.current_track is second
    assert stream.await_args_list == [
        mocker.call(first.url, loop=player.bot.loop),
        mocker.call(second.url, loop=player.bot.loop),
    ]
    assert voice.play.call_args.args == (second_source,)

    response = SimpleNamespace(send_message=mocker.AsyncMock())
    context = SimpleNamespace(
        player=player,
        author=mocker.Mock(),
        interaction=SimpleNamespace(response=response),
    )
    music = Music(mocker.Mock())
    card = mocker.Mock()
    get_card = mocker.patch.object(music, "_get_track_card", return_value=card)

    await inspect.unwrap(Music.current.callback)(music, context)

    get_card.assert_called_once_with(second, context.author)
    response.send_message.assert_awaited_once_with(embed=card, ephemeral=True)


async def test_skip_at_end_counts_current_and_clears_metadata(
    mocker: MockerFixture,
) -> None:
    only = _track("A")
    player, queue, voice = _player(mocker, [only])
    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        return_value=mocker.Mock(),
    )
    assert await player.play_next() is only
    voice.is_playing.return_value = True

    assert await player.skip_tracks(1) == (1, None)
    assert player.current_track is None
    assert queue.get_all_items("1") == []


async def test_skip_past_unavailable_successor_starts_following_track(
    mocker: MockerFixture,
) -> None:
    first, unavailable, third = (_track(name) for name in ("A", "B", "C"))
    player, _, voice = _player(mocker, [first, unavailable, third])
    first_source, third_source = mocker.Mock(), mocker.Mock()
    stream = mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        side_effect=[first_source, RuntimeError("unavailable"), third_source],
    )
    assert await player.play_next() is first
    voice.is_playing.return_value = True

    assert await player.skip_tracks(1) == (1, third)
    assert player.current_track is third
    assert [call.args[0] for call in stream.await_args_list] == [
        first.url,
        unavailable.url,
        third.url,
    ]
    assert voice.play.call_args.args == (third_source,)


async def test_failed_terminal_successor_leaves_no_stale_current_track(
    mocker: MockerFixture,
) -> None:
    first, unavailable = (_track(name) for name in ("A", "B"))
    player, queue, voice = _player(mocker, [first, unavailable])
    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        side_effect=[mocker.Mock(), RuntimeError("unavailable")],
    )
    assert await player.play_next() is first
    voice.is_playing.return_value = True

    assert await player.skip_tracks(1) == (1, None)
    assert player.current_track is None
    assert queue.get_all_items("1") == []
