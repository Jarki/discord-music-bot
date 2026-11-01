"""Regression coverage for bounded track skipping."""

import pytest
from pytest_mock import MockerFixture

from src.bot.client import Music
from src.bot.dependencies.player import Player
from src.bot.models.core import Track

pytestmark = pytest.mark.asyncio


def make_track(title: str) -> Track:
    return Track(type="youtube", title=title, url=f"https://example.com/{title}")


def make_player(mocker: MockerFixture) -> Player:
    player = Player("1", mocker.Mock(), mocker.Mock())
    player._current_track = make_track("current")
    return player


async def test_skip_rejects_count_above_limit_before_advancing(
    mocker: MockerFixture,
) -> None:
    player = make_player(mocker)
    advance = mocker.patch.object(player, "_advance_queue")
    stop = mocker.patch.object(player, "stop")
    play = mocker.patch.object(player, "_play_track", new=mocker.AsyncMock())

    with pytest.raises(ValueError, match="count must not exceed 256"):
        await player.skip_tracks(10**100)

    advance.assert_not_called()
    stop.assert_not_called()
    play.assert_not_awaited()


async def test_skip_stops_advancing_when_queue_is_exhausted(
    mocker: MockerFixture,
) -> None:
    player = make_player(mocker)
    queued = make_track("queued")
    advance = mocker.patch.object(
        player, "_advance_queue", side_effect=[queued, None]
    )
    stop = mocker.patch.object(player, "stop", return_value=True)
    play = mocker.patch.object(player, "_play_track", new=mocker.AsyncMock())

    skipped, current = await player.skip_tracks(5)

    assert skipped == 2
    assert current is None
    assert advance.call_count == 2
    stop.assert_called_once_with()
    play.assert_not_awaited()


async def test_skip_count_remains_bounded_when_queue_repeats(
    mocker: MockerFixture,
) -> None:
    player = make_player(mocker)
    repeated = make_track("repeated")
    advance = mocker.patch.object(player, "_advance_queue", return_value=repeated)
    mocker.patch.object(player, "stop", return_value=True)
    play = mocker.patch.object(player, "_play_track", new=mocker.AsyncMock())

    skipped, current = await player.skip_tracks(3)

    assert skipped == 3
    assert current is repeated
    assert advance.call_count == 3
    play.assert_awaited_once_with(repeated)


async def test_skipping_last_current_track_counts_it_as_skipped(
    mocker: MockerFixture,
) -> None:
    player = make_player(mocker)
    advance = mocker.patch.object(player, "_advance_queue", return_value=None)
    mocker.patch.object(player, "stop", return_value=True)

    skipped, current = await player.skip_tracks(1)

    assert skipped == 1
    assert current is None
    advance.assert_called_once_with(force_skip=True)


@pytest.mark.parametrize("count", [0, -1])
async def test_nonpositive_skip_count_is_a_noop(
    mocker: MockerFixture, count: int
) -> None:
    player = make_player(mocker)
    advance = mocker.patch.object(player, "_advance_queue")

    assert await player.skip_tracks(count) == (0, None)
    advance.assert_not_called()


async def test_skip_command_declares_discord_count_bounds() -> None:
    songs = next(
        parameter for parameter in Music.skip.parameters if parameter.name == "songs"
    )

    assert songs.min_value == 1
    assert songs.max_value == 256
