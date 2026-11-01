"""Behavioral regressions for continuing past unplayable queue entries."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.player import Player
from src.bot.dependencies.queue.in_memory import InMemoryQueueManager
from src.bot.dependencies.ytdlp import YTDLSource
from src.bot.models.core import QueueMode, Track

pytestmark = pytest.mark.asyncio


def _track(title: str) -> Track:
    return Track(type="youtube", title=title, url=f"https://example.com/{title}")


class FakeVoiceClient:
    def __init__(self) -> None:
        self.connected = True
        self.playing = False
        self.played: list[Any] = []
        self.after: Callable[[Exception | None], None] | None = None
        self.play_error: Exception | None = None

    def is_connected(self) -> bool:
        return self.connected

    def is_playing(self) -> bool:
        return self.playing

    def is_paused(self) -> bool:
        return False

    def play(self, source: Any, *, after: Callable[[Exception | None], None]) -> None:
        if self.play_error is not None:
            raise self.play_error
        self.played.append(source)
        self.after = after
        self.playing = True

    def stop(self) -> None:
        self.playing = False
        if self.after is not None:
            self.after(None)

    def finish(self, error: Exception | None = None) -> None:
        callback = self.after
        assert callback is not None
        self.after = None
        self.playing = False
        callback(error)


async def _flush_callback() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


def _player(
    mocker: MockerFixture,
    tracks: list[Track],
    mode: QueueMode = QueueMode.NO_REPEAT,
) -> tuple[Player, FakeVoiceClient]:
    queue = InMemoryQueueManager()
    for track in tracks:
        queue.queue_item("1", track)
    queue.set_mode("1", mode)
    bot = mocker.Mock()
    bot.loop = asyncio.get_running_loop()
    player = Player("1", queue, bot)
    voice = FakeVoiceClient()
    mocker.patch.object(player, "_get_voice_client", return_value=voice)
    return player, voice


def _source(mocker: MockerFixture, name: str) -> Any:
    source = mocker.Mock(name=name)
    source.cleanup = mocker.Mock()
    return source


async def test_completion_skips_unavailable_track_and_starts_later_track(
    mocker: MockerFixture,
) -> None:
    first, unavailable, third = (_track(name) for name in ("A", "B", "C"))
    player, voice = _player(mocker, [first, unavailable, third])
    first_source = _source(mocker, "A source")
    third_source = _source(mocker, "C source")
    stream = mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(
            side_effect=[first_source, RuntimeError("unavailable"), third_source]
        ),
    )

    assert await player.play_next() is first
    voice.finish()
    await _flush_callback()

    assert player.current_track is third
    assert voice.played == [first_source, third_source]
    assert [call.args[0] for call in stream.await_args_list] == [
        first.url,
        unavailable.url,
        third.url,
    ]


async def test_initial_failure_continues_to_first_playable_track(
    mocker: MockerFixture,
) -> None:
    unavailable, valid = _track("unavailable"), _track("valid")
    player, voice = _player(mocker, [unavailable, valid])
    valid_source = _source(mocker, "valid source")
    mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(side_effect=[RuntimeError("unavailable"), valid_source]),
    )

    assert await player.play_next() is valid
    assert player.current_track is valid
    assert voice.played == [valid_source]


async def test_skip_continues_past_failed_successor(mocker: MockerFixture) -> None:
    current, unavailable, valid = (
        _track(name) for name in ("current", "unavailable", "valid")
    )
    player, voice = _player(mocker, [current, unavailable, valid])
    current_source = _source(mocker, "current source")
    valid_source = _source(mocker, "valid source")
    mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(
            side_effect=[current_source, RuntimeError("unavailable"), valid_source]
        ),
    )

    assert await player.play_next() is current
    skipped, started = await player.skip_tracks(1)

    assert skipped == 1
    assert started is valid
    assert player.current_track is valid
    assert voice.played == [current_source, valid_source]


@pytest.mark.parametrize(
    "mode",
    [QueueMode.REPEAT_SINGLE, QueueMode.REPEAT_QUEUE, QueueMode.SHUFFLE],
)
async def test_all_failed_repeating_queue_attempts_each_entry_once(
    mocker: MockerFixture,
    mode: QueueMode,
) -> None:
    tracks = [_track(name) for name in ("A", "B", "C")]
    player, voice = _player(mocker, tracks, mode)
    stream = mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(side_effect=RuntimeError("unavailable")),
    )

    assert await player.play_next() is None
    assert player.current_track is None
    assert voice.played == []
    assert stream.await_count == len(tracks)
    assert len({call.args[0] for call in stream.await_args_list}) == len(tracks)


async def test_clear_while_retry_is_loading_cannot_restart_playback(
    mocker: MockerFixture,
) -> None:
    first, second = _track("first"), _track("second")
    player, voice = _player(mocker, [first, second])
    loading = asyncio.Event()
    release = asyncio.Event()
    second_source = _source(mocker, "second source")

    async def extract(url: str, *, loop: Any) -> Any:
        del loop
        if url == first.url:
            raise RuntimeError("unavailable")
        loading.set()
        await release.wait()
        return second_source

    mocker.patch.object(YTDLSource, "stream_from_url", side_effect=extract)
    request = asyncio.create_task(player.play_next())
    await loading.wait()

    player.clear_queue()
    release.set()

    assert await request is None
    assert player.current_track is None
    assert voice.played == []
    second_source.cleanup.assert_called_once_with()


async def test_source_is_cleaned_when_voice_rejects_start(
    mocker: MockerFixture,
) -> None:
    track = _track("rejected")
    player, voice = _player(mocker, [track])
    source = _source(mocker, "rejected source")
    voice.play_error = RuntimeError("voice rejected source")
    mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(return_value=source),
    )

    assert await player.play_next() is None
    assert player.current_track is None
    source.cleanup.assert_called_once_with()


async def test_playback_error_moves_past_failed_repeat_single_source(
    mocker: MockerFixture,
) -> None:
    broken, valid = _track("broken"), _track("valid")
    player, voice = _player(mocker, [broken, valid], QueueMode.REPEAT_SINGLE)
    broken_source = _source(mocker, "broken source")
    valid_source = _source(mocker, "valid source")
    mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(side_effect=[broken_source, valid_source]),
    )

    assert await player.play_next() is broken
    voice.finish(RuntimeError("decoder failed"))
    await _flush_callback()

    assert player.current_track is valid
    assert voice.played == [broken_source, valid_source]


async def test_failed_only_repeat_single_entry_is_not_retried(
    mocker: MockerFixture,
) -> None:
    broken = _track("broken")
    player, voice = _player(mocker, [broken], QueueMode.REPEAT_SINGLE)
    broken_source = _source(mocker, "broken source")
    stream = mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(return_value=broken_source),
    )

    assert await player.play_next() is broken
    voice.finish(RuntimeError("decoder failed"))
    await _flush_callback()

    assert player.current_track is None
    assert voice.played == [broken_source]
    stream.assert_awaited_once_with(broken.url, loop=player.bot.loop)


async def test_callback_failure_and_extraction_failure_do_not_wrap_to_broken_track(
    mocker: MockerFixture,
) -> None:
    broken, unavailable = _track("broken"), _track("unavailable")
    player, voice = _player(
        mocker,
        [broken, unavailable],
        QueueMode.REPEAT_QUEUE,
    )
    broken_source = _source(mocker, "broken source")
    stream = mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(side_effect=[broken_source, RuntimeError("unavailable")]),
    )

    assert await player.play_next() is broken
    voice.finish(RuntimeError("decoder failed"))
    await _flush_callback()

    assert player.current_track is None
    assert voice.played == [broken_source]
    assert [call.args[0] for call in stream.await_args_list] == [
        broken.url,
        unavailable.url,
    ]


async def test_successive_callback_failures_share_bounded_attempt_history(
    mocker: MockerFixture,
) -> None:
    unavailable, broken_b, broken_c = (_track(name) for name in ("A", "B", "C"))
    player, voice = _player(
        mocker,
        [unavailable, broken_b, broken_c],
        QueueMode.REPEAT_QUEUE,
    )
    b_source = _source(mocker, "B source")
    c_source = _source(mocker, "C source")
    retried_b_source = _source(mocker, "retried B source")
    stream = mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(
            side_effect=[
                RuntimeError("A unavailable"),
                b_source,
                c_source,
                retried_b_source,
            ]
        ),
    )

    assert await player.play_next() is broken_b
    voice.finish(RuntimeError("B decoder failed"))
    await _flush_callback()
    assert player.current_track is broken_c

    voice.finish(RuntimeError("C decoder failed"))
    await _flush_callback()

    assert player.current_track is None
    assert voice.played == [b_source, c_source]
    assert [call.args[0] for call in stream.await_args_list] == [
        unavailable.url,
        broken_b.url,
        broken_c.url,
    ]

    assert await player.play_next() is broken_b
    assert player.current_track is broken_b
    assert voice.played == [b_source, c_source, retried_b_source]
    assert [call.args[0] for call in stream.await_args_list] == [
        unavailable.url,
        broken_b.url,
        broken_c.url,
        broken_b.url,
    ]


async def test_normal_repeat_single_completion_still_replays_track(
    mocker: MockerFixture,
) -> None:
    repeated = _track("repeated")
    player, voice = _player(mocker, [repeated], QueueMode.REPEAT_SINGLE)
    first_source = _source(mocker, "first source")
    second_source = _source(mocker, "second source")
    mocker.patch.object(
        YTDLSource,
        "stream_from_url",
        new=mocker.AsyncMock(side_effect=[first_source, second_source]),
    )

    assert await player.play_next() is repeated
    voice.finish()
    await _flush_callback()

    assert player.current_track is repeated
    assert voice.played == [first_source, second_source]
