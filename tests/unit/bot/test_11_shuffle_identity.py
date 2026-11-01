"""Regression tests for identity-preserving shuffle mode transitions."""

import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.queue.in_memory import InMemoryQueueManager
from src.bot.models import QueueMode, Track

QUEUE_ID = "shuffle-identity"


def _manager_with_tracks() -> tuple[InMemoryQueueManager, list[Track]]:
    manager = InMemoryQueueManager()
    tracks = [
        Track(type="youtube", title=title, url=f"https://example.com/{title}")
        for title in ("A", "B", "C")
    ]
    for track in tracks:
        manager.queue_item(QUEUE_ID, track)
    return manager, tracks


def _shuffle_to_201(order: list[int]) -> None:
    if order:
        order[:] = [2, 0, 1]


def test_entering_shuffle_preserves_current_track_without_duplicate(
    mocker: MockerFixture,
) -> None:
    manager, tracks = _manager_with_tracks()
    assert manager.get_next(QUEUE_ID) is tracks[0]
    assert manager.get_next(QUEUE_ID) is tracks[1]
    mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=_shuffle_to_201,
    )

    manager.set_mode(QUEUE_ID, QueueMode.SHUFFLE)

    # B is at the end of [C, A, B], so advancing wraps to C rather than
    # replaying B or resetting playback to the start of the permutation.
    assert manager.get_next(QUEUE_ID) is tracks[2]


@pytest.mark.parametrize(
    ("mode", "next_index", "raises_at_end"),
    [
        (QueueMode.REPEAT_SINGLE, 2, False),
        (QueueMode.NO_REPEAT, None, True),
        (QueueMode.REPEAT_QUEUE, 0, False),
    ],
)
def test_leaving_shuffle_translates_current_track_for_every_exit_mode(
    mocker: MockerFixture,
    mode: QueueMode,
    next_index: int | None,
    raises_at_end: bool,
) -> None:
    manager, tracks = _manager_with_tracks()
    mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=_shuffle_to_201,
    )
    manager.set_mode(QUEUE_ID, QueueMode.SHUFFLE)
    assert manager.get_next(QUEUE_ID) is tracks[2]

    manager.set_mode(QUEUE_ID, mode)

    if raises_at_end:
        with pytest.raises(RuntimeError, match="No next item available"):
            manager.get_next(QUEUE_ID)
    else:
        assert next_index is not None
        assert manager.get_next(QUEUE_ID) is tracks[next_index]


def test_leaving_shuffle_at_nonterminal_item_advances_logical_queue(
    mocker: MockerFixture,
) -> None:
    manager, tracks = _manager_with_tracks()
    mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=_shuffle_to_201,
    )
    manager.set_mode(QUEUE_ID, QueueMode.SHUFFLE)
    assert manager.get_next(QUEUE_ID) is tracks[2]
    assert manager.get_next(QUEUE_ID) is tracks[0]

    manager.set_mode(QUEUE_ID, QueueMode.NO_REPEAT)

    assert manager.get_next(QUEUE_ID) is tracks[1]


@pytest.mark.parametrize(
    "mode",
    [QueueMode.REPEAT_SINGLE, QueueMode.NO_REPEAT, QueueMode.REPEAT_QUEUE],
)
def test_mode_changes_before_playback_do_not_skip_first_track(
    mocker: MockerFixture, mode: QueueMode
) -> None:
    manager, tracks = _manager_with_tracks()
    mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=_shuffle_to_201,
    )

    manager.set_mode(QUEUE_ID, QueueMode.SHUFFLE)
    manager.set_mode(QUEUE_ID, mode)

    assert manager.get_next(QUEUE_ID) is tracks[0]


def test_setting_shuffle_mode_again_is_no_op(mocker: MockerFixture) -> None:
    manager, tracks = _manager_with_tracks()
    shuffle = mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=_shuffle_to_201,
    )
    manager.set_mode(QUEUE_ID, QueueMode.SHUFFLE)
    assert manager.get_next(QUEUE_ID) is tracks[2]

    manager.set_mode(QUEUE_ID, QueueMode.SHUFFLE)

    assert shuffle.call_count == 1
    assert manager.get_next(QUEUE_ID) is tracks[0]


def test_empty_queue_mode_boundaries_remain_before_start(
    mocker: MockerFixture,
) -> None:
    manager = InMemoryQueueManager()
    shuffle = mocker.patch(
        "src.bot.dependencies.queue.in_memory.random.shuffle",
        side_effect=_shuffle_to_201,
    )

    manager.set_mode(QUEUE_ID, QueueMode.SHUFFLE)
    manager.set_mode(QUEUE_ID, QueueMode.REPEAT_QUEUE)

    assert shuffle.call_count == 1
    assert manager.get_current_position(QUEUE_ID) == -1
    with pytest.raises(RuntimeError, match="Cannot navigate empty queue"):
        manager.get_next(QUEUE_ID)
