"""Regression tests for bounded active queue capacity."""

import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.queue.in_memory import InMemoryQueueManager
from src.bot.models import QueueMode, Track

QUEUE_ID = "queue-capacity"


def _track(index: int) -> Track:
    return Track(
        type="youtube",
        title=f"Track {index}",
        url=f"https://example.com/{index}",
        track_id=str(index),
    )


@pytest.mark.parametrize("total", [257, 300])
def test_normal_playback_releases_consumed_tracks_for_lifetime_additions(
    total: int,
) -> None:
    manager = InMemoryQueueManager()

    for index in range(total):
        track = _track(index)
        manager.queue_item(QUEUE_ID, track)
        assert manager.get_next(QUEUE_ID) is track

    with pytest.raises(RuntimeError, match="No next item available"):
        manager.get_next(QUEUE_ID)
    assert manager.get_all_items(QUEUE_ID) == []
    assert manager.get_current_position(QUEUE_ID) == -1


@pytest.mark.parametrize("started", [False, True])
def test_capacity_counts_only_active_current_and_pending(started: bool) -> None:
    manager = InMemoryQueueManager()
    tracks = [_track(index) for index in range(manager.MAX_QUEUE_SIZE)]
    for track in tracks:
        manager.queue_item(QUEUE_ID, track)

    if started:
        assert manager.get_next(QUEUE_ID) is tracks[0]

    with pytest.raises(RuntimeError, match="Queue is at maximum capacity"):
        manager.queue_item(QUEUE_ID, _track(manager.MAX_QUEUE_SIZE))

    if started:
        assert manager.get_next(QUEUE_ID) is tracks[1]
        replacement = _track(manager.MAX_QUEUE_SIZE)
        assert manager.queue_item(QUEUE_ID, replacement) is replacement
        assert len(manager.get_all_items(QUEUE_ID)) == manager.MAX_QUEUE_SIZE


def test_exhausting_normal_queue_releases_current_and_accepts_new_track() -> None:
    manager = InMemoryQueueManager()
    first = _track(0)
    manager.queue_item(QUEUE_ID, first)
    assert manager.get_next(QUEUE_ID) is first

    with pytest.raises(RuntimeError, match="No next item available"):
        manager.get_next(QUEUE_ID)

    second = _track(1)
    manager.queue_item(QUEUE_ID, second)
    assert manager.get_next(QUEUE_ID) is second


def test_normal_previous_has_no_consumed_history() -> None:
    manager = InMemoryQueueManager()
    tracks = [_track(index) for index in range(2)]
    for track in tracks:
        manager.queue_item(QUEUE_ID, track)
    assert manager.get_next(QUEUE_ID) is tracks[0]
    assert manager.get_next(QUEUE_ID) is tracks[1]

    with pytest.raises(RuntimeError, match="No previous item available"):
        manager.get_prev(QUEUE_ID)
    assert manager.get_all_items(QUEUE_ID) == [tracks[1]]


@pytest.mark.parametrize(
    "mode",
    [QueueMode.REPEAT_QUEUE, QueueMode.REPEAT_SINGLE, QueueMode.SHUFFLE],
)
def test_repeating_modes_retain_all_tracks(
    mocker: MockerFixture, mode: QueueMode
) -> None:
    manager = InMemoryQueueManager()
    tracks = [_track(index) for index in range(3)]
    for track in tracks:
        manager.queue_item(QUEUE_ID, track)
    mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=lambda order: order.reverse(),
    )
    manager.set_mode(QUEUE_ID, mode)

    for _ in range(5):
        manager.get_next(QUEUE_ID)

    assert manager.get_all_items(QUEUE_ID) == tracks


@pytest.mark.parametrize("source_mode", [QueueMode.REPEAT_QUEUE, QueueMode.SHUFFLE])
def test_entering_normal_preserves_current_and_discards_only_prior_items(
    mocker: MockerFixture, source_mode: QueueMode
) -> None:
    manager = InMemoryQueueManager()
    tracks = [_track(index) for index in range(4)]
    for track in tracks:
        manager.queue_item(QUEUE_ID, track)
    mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=lambda _order: None,
    )
    manager.set_mode(QUEUE_ID, source_mode)
    assert manager.get_next(QUEUE_ID) is tracks[0]
    assert manager.get_next(QUEUE_ID) is tracks[1]

    manager.set_mode(QUEUE_ID, QueueMode.NO_REPEAT)

    assert manager.get_all_items(QUEUE_ID) == tracks[1:]
    assert manager.get_current_position(QUEUE_ID) == 0
    assert manager.get_next(QUEUE_ID) is tracks[2]


def test_leaving_normal_preserves_active_current_identity(
    mocker: MockerFixture,
) -> None:
    manager = InMemoryQueueManager()
    tracks = [_track(index) for index in range(3)]
    for track in tracks:
        manager.queue_item(QUEUE_ID, track)
    assert manager.get_next(QUEUE_ID) is tracks[0]
    assert manager.get_next(QUEUE_ID) is tracks[1]
    mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=lambda order: order.reverse(),
    )

    manager.set_mode(QUEUE_ID, QueueMode.SHUFFLE)

    assert manager.get_all_items(QUEUE_ID) == tracks[1:]
    assert manager.get_next(QUEUE_ID) is tracks[2]


def test_clear_after_consumption_resets_active_state() -> None:
    manager = InMemoryQueueManager()
    tracks = [_track(index) for index in range(2)]
    for track in tracks:
        manager.queue_item(QUEUE_ID, track)
    assert manager.get_next(QUEUE_ID) is tracks[0]

    manager.reset_queue(QUEUE_ID)

    assert manager.get_all_items(QUEUE_ID) == []
    assert manager.get_current_position(QUEUE_ID) == -1
