"""Deterministic playback lifecycle regressions."""

import asyncio
from typing import Any

import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.player import Player
from src.bot.dependencies.queue.in_memory import InMemoryQueueManager
from src.bot.models.core import Track


def _track(name: str) -> Track:
    return Track(type="youtube", title=name, url=f"https://example.com/{name}")


def _player(mocker: MockerFixture, tracks: list[Track]) -> tuple[Player, Any, Any]:
    queue = InMemoryQueueManager()
    for track in tracks:
        queue.queue_item("1", track)
    mocker.spy(queue, "get_next")
    mocker.spy(queue, "reset_queue")
    voice = mocker.Mock()
    voice.is_playing.return_value = False
    voice.is_paused.return_value = False
    voice.is_connected.return_value = True
    bot = mocker.Mock()
    bot.loop = asyncio.get_running_loop()
    player = Player("1", queue, bot)
    mocker.patch.object(player, "_get_voice_client", return_value=voice)
    return player, queue, voice


async def _flush_callbacks() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["clear", "stop"])
async def test_invalidation_rejects_suspended_start_and_cleans_source(
    mocker: MockerFixture, operation: str
) -> None:
    player, queue, voice = _player(mocker, [_track("first")])
    resolution_started = asyncio.Event()
    release_resolution = asyncio.Event()
    source = mocker.Mock()

    async def resolve(*args: object, **kwargs: object) -> Any:
        resolution_started.set()
        await release_resolution.wait()
        return source

    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url", side_effect=resolve
    )
    start = asyncio.create_task(player.play_next())
    await resolution_started.wait()

    if operation == "clear":
        player.clear_queue()
        queue.reset_queue.assert_called_once_with("1")
    else:
        player.stop()
    release_resolution.set()

    assert await start is None
    voice.play.assert_not_called()
    source.cleanup.assert_called_once_with()
    assert player.current_track is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["stop", "clear"])
@pytest.mark.parametrize("queued_operation", ["play", "skip"])
async def test_invalidation_cancels_request_waiting_for_playback_lock(
    mocker: MockerFixture, operation: str, queued_operation: str
) -> None:
    first, queued = _track("first"), _track("queued")
    player, queue, voice = _player(mocker, [first, queued])
    resolution_started = asyncio.Event()
    release_resolution = asyncio.Event()
    source = mocker.Mock()

    async def resolve(*args: object, **kwargs: object) -> Any:
        resolution_started.set()
        await release_resolution.wait()
        return source

    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url", side_effect=resolve
    )
    loading = asyncio.create_task(player.play_next())
    await resolution_started.wait()
    if queued_operation == "play":
        waiting = asyncio.create_task(player.play_next())
    else:
        waiting = asyncio.create_task(player.skip_tracks(1))
    await asyncio.sleep(0)

    if operation == "clear":
        player.clear_queue()
    else:
        player.stop()
    release_resolution.set()

    assert await loading is None
    if queued_operation == "play":
        assert await waiting is None
    else:
        assert await waiting == (0, None)
    queue.get_next.assert_called_once_with("1", force_skip=False)
    voice.play.assert_not_called()
    source.cleanup.assert_called_once_with()


@pytest.mark.asyncio
async def test_overlapping_starts_advance_queue_once(mocker: MockerFixture) -> None:
    track = _track("first")
    player, queue, voice = _player(mocker, [track])
    resolution_started = asyncio.Event()
    release_resolution = asyncio.Event()
    source = mocker.Mock()

    async def resolve(*args: object, **kwargs: object) -> Any:
        resolution_started.set()
        await release_resolution.wait()
        return source

    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url", side_effect=resolve
    )
    first = asyncio.create_task(player.play_next())
    await resolution_started.wait()
    second = asyncio.create_task(player.play_next())
    await asyncio.sleep(0)
    release_resolution.set()

    assert await first is track
    assert await second is track
    queue.get_next.assert_called_once_with("1", force_skip=False)
    voice.play.assert_called_once()
    source.cleanup.assert_not_called()


@pytest.mark.asyncio
async def test_replaced_voice_client_can_start_before_old_callback(
    mocker: MockerFixture,
) -> None:
    first, second, ghost = (_track(name) for name in ("first", "second", "ghost"))
    player, queue, old_voice = _player(mocker, [first, second, ghost])
    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        side_effect=[mocker.Mock(), mocker.Mock()],
    )
    assert await player.play_next() is first
    old_after = old_voice.play.call_args.kwargs["after"]

    new_voice = mocker.Mock()
    new_voice.is_playing.return_value = False
    new_voice.is_paused.return_value = False
    new_voice.is_connected.return_value = True
    mocker.patch.object(player, "_get_voice_client", return_value=new_voice)

    assert await player.play_next() is second
    assert player.current_track is second
    old_after(None)
    await _flush_callbacks()

    assert player.current_track is second
    queue.get_next.assert_has_calls(
        [
            mocker.call("1", force_skip=False),
            mocker.call("1", force_skip=False),
        ]
    )
    assert queue.get_next.call_count == 2
    new_voice.play.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["playing", "paused"])
async def test_active_or_paused_play_next_does_not_advance(
    mocker: MockerFixture, state: str
) -> None:
    player, queue, voice = _player(mocker, [_track("unconsumed")])
    getattr(voice, f"is_{state}").return_value = True

    assert await player.play_next() is None
    queue.get_next.assert_not_called()
    voice.play.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_during_resolution_releases_track_ownership(
    mocker: MockerFixture,
) -> None:
    first, second = _track("first"), _track("second")
    player, _, voice = _player(mocker, [first, second])
    resolution_started = asyncio.Event()
    release_resolution = asyncio.Event()
    rejected_source, next_source = mocker.Mock(), mocker.Mock()
    calls = 0

    async def resolve(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            resolution_started.set()
            await release_resolution.wait()
            return rejected_source
        return next_source

    stream = mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        side_effect=resolve,
    )
    start = asyncio.create_task(player.play_next())
    await resolution_started.wait()
    voice.is_connected.return_value = False
    release_resolution.set()

    assert await start is None
    assert player.current_track is None
    rejected_source.cleanup.assert_called_once_with()

    voice.is_connected.return_value = True
    assert await player.play_next() is second
    assert stream.call_count == 2
    voice.play.assert_called_once()


@pytest.mark.asyncio
async def test_delayed_callback_after_clear_does_not_advance(
    mocker: MockerFixture,
) -> None:
    first, ghost = _track("first"), _track("ghost")
    player, queue, voice = _player(mocker, [first, ghost])
    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        return_value=mocker.Mock(),
    )
    assert await player.play_next() is first
    after = voice.play.call_args.kwargs["after"]

    player.clear_queue()
    after(None)
    await _flush_callbacks()

    assert player.current_track is None
    assert queue.get_next.call_count == 1


@pytest.mark.asyncio
async def test_play_rejection_cleans_source(mocker: MockerFixture) -> None:
    track = _track("first")
    player, _, voice = _player(mocker, [track])
    source = mocker.Mock()
    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        return_value=source,
    )
    voice.play.side_effect = RuntimeError("already playing")

    assert await player.play_next() is None
    source.cleanup.assert_called_once_with()
    assert player.current_track is None


@pytest.mark.asyncio
async def test_two_skips_ignore_callbacks_delivered_in_reverse_order(
    mocker: MockerFixture,
) -> None:
    first, second, third = (_track(name) for name in ("first", "second", "third"))
    player, queue, voice = _player(mocker, [first, second, third])
    mocker.patch(
        "src.bot.dependencies.player.YTDLSource.stream_from_url",
        side_effect=[mocker.Mock(), mocker.Mock(), mocker.Mock()],
    )

    assert await player.play_next() is first
    first_after = voice.play.call_args.kwargs["after"]
    voice.is_playing.return_value = True
    assert await player.skip_tracks(1) == (1, second)
    second_after = voice.play.call_args.kwargs["after"]
    assert await player.skip_tracks(1) == (1, third)

    second_after(None)
    first_after(None)
    await _flush_callbacks()

    assert player.current_track is third
    assert queue.get_next.call_count == 3
