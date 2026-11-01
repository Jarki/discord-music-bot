"""Regressions for paused state across playback lifecycle transitions."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.player import Player
from src.bot.dependencies.queue.in_memory import InMemoryQueueManager
from src.bot.models.core import Track


class FakeVoiceClient:
    """Stateful voice client double implementing the playback controls Player uses."""

    def __init__(self) -> None:
        self.connected = True
        self.playing = False
        self.paused = False
        self.after: Callable[[Exception | None], None] | None = None
        self.played_sources: list[Any] = []

    def is_connected(self) -> bool:
        return self.connected

    def is_playing(self) -> bool:
        return self.playing

    def is_paused(self) -> bool:
        return self.paused

    def play(self, source: Any, *, after: Callable[[Exception | None], None]) -> None:
        self.played_sources.append(source)
        self.after = after
        self.playing = True
        self.paused = False

    def pause(self) -> None:
        if self.playing:
            self.playing = False
            self.paused = True

    def resume(self) -> None:
        if self.paused:
            self.paused = False
            self.playing = True

    def stop(self) -> None:
        self.playing = False
        self.paused = False


def _track(name: str) -> Track:
    return Track(type="youtube", title=name, url=f"https://example.com/{name}")


def _player(
    mocker: MockerFixture,
) -> tuple[Player, InMemoryQueueManager, FakeVoiceClient]:
    queue = InMemoryQueueManager()
    voice = FakeVoiceClient()
    bot = mocker.Mock()
    bot.loop = asyncio.get_running_loop()
    player = Player("1", queue, bot)
    mocker.patch.object(player, "_get_voice_client", return_value=voice)
    return player, queue, voice


def _mock_extraction(mocker: MockerFixture, *sources: Any) -> Any:
    return mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        new=mocker.AsyncMock(side_effect=sources),
    )


@pytest.mark.asyncio
async def test_pause_clear_then_new_queue_starts_from_queue_helper(
    mocker: MockerFixture,
) -> None:
    player, _, voice = _player(mocker)
    first, replacement = _track("first"), _track("replacement")
    first_source, replacement_source = mocker.Mock(), mocker.Mock()
    extraction = _mock_extraction(mocker, first_source, replacement_source)

    await player.add_track(first)
    assert await player.play_next() is first
    assert player.pause() is True
    assert player.is_paused is True

    player.clear_queue()
    assert player.is_paused is False
    await player.add_track(replacement)

    started = None
    if not player.is_playing() and not player.is_paused:
        started = await player.play_next()

    assert started is replacement
    assert player.current_track is replacement
    assert voice.playing is True
    assert voice.paused is False
    assert voice.played_sources == [first_source, replacement_source]
    assert extraction.await_count == 2


@pytest.mark.asyncio
async def test_pause_then_skip_starts_unpaused_successor(
    mocker: MockerFixture,
) -> None:
    player, _, voice = _player(mocker)
    first, successor = _track("first"), _track("successor")
    _mock_extraction(mocker, mocker.Mock(), mocker.Mock())
    await player.add_track(first)
    await player.add_track(successor)

    assert await player.play_next() is first
    assert player.pause() is True

    skipped, started = await player.skip_tracks(1)

    assert (skipped, started) == (1, successor)
    assert player.current_track is successor
    assert player.is_paused is False
    assert voice.playing is True


@pytest.mark.asyncio
async def test_failed_successor_after_paused_skip_is_not_stale_paused(
    mocker: MockerFixture,
) -> None:
    player, _, voice = _player(mocker)
    first, successor = _track("first"), _track("successor")
    extraction = mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        new=mocker.AsyncMock(
            side_effect=[mocker.Mock(), RuntimeError("extraction failed")]
        ),
    )
    await player.add_track(first)
    await player.add_track(successor)

    assert await player.play_next() is first
    assert player.pause() is True
    assert await player.skip_tracks(1) == (1, None)

    assert extraction.await_count == 2
    assert player.current_track is None
    assert player.is_paused is False
    assert voice.playing is False


@pytest.mark.asyncio
async def test_stop_clears_active_pause_state(mocker: MockerFixture) -> None:
    player, _, voice = _player(mocker)
    track = _track("first")
    _mock_extraction(mocker, mocker.Mock())
    await player.add_track(track)

    assert await player.play_next() is track
    assert player.pause() is True
    assert player.stop() is True

    assert player.current_track is None
    assert player.is_paused is False
    assert voice.playing is False
    assert voice.paused is False


@pytest.mark.asyncio
async def test_resume_active_pause_remains_synchronous(mocker: MockerFixture) -> None:
    player, _, voice = _player(mocker)
    track = _track("first")
    _mock_extraction(mocker, mocker.Mock())
    await player.add_track(track)

    assert await player.play_next() is track
    assert player.pause() is True
    assert player.resume() is True

    assert player.is_paused is False
    assert voice.playing is True
    assert voice.paused is False


@pytest.mark.asyncio
async def test_disconnect_and_voice_replacement_do_not_report_old_pause(
    mocker: MockerFixture,
) -> None:
    player, _, old_voice = _player(mocker)
    track = _track("first")
    _mock_extraction(mocker, mocker.Mock())
    await player.add_track(track)
    assert await player.play_next() is track
    assert player.pause() is True

    old_voice.connected = False
    assert player.is_paused is False

    replacement = FakeVoiceClient()
    mocker.patch.object(player, "_get_voice_client", return_value=replacement)
    assert player.is_paused is False


@pytest.mark.asyncio
async def test_missing_voice_client_reports_not_paused(mocker: MockerFixture) -> None:
    bot = mocker.Mock()
    bot.loop = asyncio.get_running_loop()
    bot.get_guild.return_value = None
    player = Player("1", InMemoryQueueManager(), bot)

    assert player.is_paused is False
