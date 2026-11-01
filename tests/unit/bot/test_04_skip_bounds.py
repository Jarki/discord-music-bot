"""Behavioral coverage for bounded skips against the real playback state machine."""

import asyncio
from io import BytesIO
from typing import Any

import discord
import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.player import Player
from src.bot.dependencies.queue.in_memory import InMemoryQueueManager
from src.bot.models.core import QueueMode, Track

pytestmark = pytest.mark.asyncio


def make_track(title: str) -> Track:
    return Track(
        type="youtube", title=title, url=f"https://www.youtube.com/watch?v={title}"
    )


def make_player(mocker: MockerFixture) -> tuple[Player, InMemoryQueueManager, Any]:
    queue = InMemoryQueueManager()
    voice = mocker.Mock(spec=discord.VoiceClient)
    state: dict[str, Any] = {"playing": False, "source": None}
    voice.is_playing.side_effect = lambda: state["playing"]
    voice.is_paused.return_value = False
    voice.is_connected.return_value = True

    def play(source: discord.AudioSource, **_kwargs: Any) -> None:
        state["playing"] = True
        state["source"] = source

    def stop() -> None:
        state["playing"] = False
        if state["source"] is not None:
            state["source"].cleanup()
            state["source"] = None

    voice.play.side_effect = play
    voice.stop.side_effect = stop
    bot = mocker.Mock()
    bot.loop = asyncio.get_running_loop()
    player = Player("1", queue, bot)
    mocker.patch.object(player, "_get_voice_client", return_value=voice)
    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        side_effect=lambda *_args, **_kwargs: discord.PCMAudio(BytesIO()),
    )
    return player, queue, voice


async def test_skip_rejects_count_above_limit_without_losing_current_or_successor(
    mocker: MockerFixture,
) -> None:
    player, queue, voice = make_player(mocker)
    first, second = make_track("first"), make_track("second")
    queue.queue_item("1", first)
    queue.queue_item("1", second)
    await player.play_next()

    with pytest.raises(ValueError):
        await player.skip_tracks(257)

    assert player.current_track is first
    assert voice.is_playing()
    assert await player.skip_tracks(1) == (1, second)
    player.stop()


async def test_skip_stops_at_exhaustion_and_counts_current_track(
    mocker: MockerFixture,
) -> None:
    player, queue, voice = make_player(mocker)
    for title in ("first", "second"):
        queue.queue_item("1", make_track(title))
    await player.play_next()

    assert await player.skip_tracks(5) == (2, None)
    assert player.current_track is None
    assert not voice.is_playing()
    assert queue.get_all_items("1") == []


async def test_maximum_skip_count_advances_repeat_queue_correctly(
    mocker: MockerFixture,
) -> None:
    player, queue, _voice = make_player(mocker)
    tracks = [make_track(title) for title in ("A", "B", "C")]
    for track in tracks:
        queue.queue_item("1", track)
    player.set_mode(QueueMode.REPEAT_QUEUE)
    await player.play_next()

    assert await player.skip_tracks(256) == (256, tracks[1])
    assert player.current_track is tracks[1]
    assert queue.get_all_items("1") == tracks
    player.stop()


async def test_skipping_last_current_track_counts_it_as_skipped(
    mocker: MockerFixture,
) -> None:
    player, queue, voice = make_player(mocker)
    queue.queue_item("1", make_track("last"))
    await player.play_next()

    assert await player.skip_tracks(1) == (1, None)
    assert player.current_track is None
    assert not voice.is_playing()


@pytest.mark.parametrize("previously_exhausted", [False, True])
async def test_idle_empty_queue_does_not_report_a_skip(
    mocker: MockerFixture, previously_exhausted: bool
) -> None:
    player, queue, _voice = make_player(mocker)
    if previously_exhausted:
        queue.queue_item("1", make_track("exhausted"))
        queue.get_next("1")
        with pytest.raises(RuntimeError):
            queue.get_next("1")

    assert await player.skip_tracks(1) == (0, None)
    assert player.current_track is None


async def test_idle_player_counts_successful_advance_in_real_queue(
    mocker: MockerFixture,
) -> None:
    player, queue, voice = make_player(mocker)
    queued = queue.queue_item("1", make_track("queued"))

    assert await player.skip_tracks(1) == (1, queued)
    assert player.current_track is queued
    assert voice.is_playing()
    player.stop()


@pytest.mark.parametrize("count", [0, -1])
async def test_nonpositive_skip_count_preserves_active_playback(
    mocker: MockerFixture, count: int
) -> None:
    player, queue, voice = make_player(mocker)
    current = queue.queue_item("1", make_track("current"))
    await player.play_next()

    assert await player.skip_tracks(count) == (0, None)
    assert player.current_track is current
    assert voice.is_playing()
    player.stop()
