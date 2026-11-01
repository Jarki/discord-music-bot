"""Interaction acknowledgement ordering regressions for issue 08."""

import asyncio
import inspect
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from src.bot.client import Music
from src.bot.components.search_view import SearchResultsView
from src.bot.models.core import SearchResult, Track


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("skip_result", "expected_content", "ephemeral"),
    [
        (
            (1, Track(type="youtube", title="Next", url="https://next")),
            "Skipped 1 track(s). Now playing: formatted",
            False,
        ),
        ((2, None), "Skipped 2 track(s). No more tracks in the queue.", False),
        ((0, None), "Could not skip tracks.", True),
    ],
)
async def test_skip_defers_before_slow_skip_and_uses_followup(
    mocker: MockerFixture,
    skip_result: tuple[int, Track | None],
    expected_content: str,
    ephemeral: bool,
) -> None:
    acknowledged = asyncio.Event()
    skip_started = asyncio.Event()
    release_skip = asyncio.Event()

    async def defer(*, ephemeral: bool) -> None:
        assert ephemeral is True
        acknowledged.set()

    async def skip_tracks(_songs: int) -> tuple[int, Track | None]:
        skip_started.set()
        await release_skip.wait()
        return skip_result

    response = SimpleNamespace(
        defer=mocker.AsyncMock(side_effect=defer),
        send_message=mocker.AsyncMock(),
        is_done=mocker.Mock(return_value=False),
    )
    followup = SimpleNamespace(send=mocker.AsyncMock())
    player = SimpleNamespace(
        is_playing=mocker.Mock(return_value=True),
        is_paused=False,
        skip_tracks=mocker.AsyncMock(side_effect=skip_tracks),
    )
    context = SimpleNamespace(
        player=player,
        interaction=SimpleNamespace(
            response=response,
            followup=followup,
            edit_original_response=mocker.AsyncMock(),
            delete_original_response=mocker.AsyncMock(),
        ),
        author=mocker.Mock(),
    )
    music = Music(mocker.Mock())
    mocker.patch.object(music, "_format_track_link", return_value="formatted")
    card = mocker.patch.object(music, "_get_track_card", return_value=mocker.Mock())

    task = asyncio.create_task(inspect.unwrap(Music.skip.callback)(music, context, 2))
    await skip_started.wait()

    assert acknowledged.is_set()
    response.defer.assert_awaited_once_with(ephemeral=True)
    response.send_message.assert_not_awaited()

    release_skip.set()
    await task

    expected_kwargs: dict[str, object] = {"ephemeral": ephemeral}
    if skip_result[1] is not None:
        expected_kwargs["embed"] = card.return_value
    context.interaction.delete_original_response.assert_awaited_once_with()
    followup.send.assert_awaited_once_with(expected_content, **expected_kwargs)
    context.interaction.edit_original_response.assert_not_awaited()
    response.send_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_ephemeral", [False, True])
@pytest.mark.parametrize(
    ("skip_result", "expected_ephemeral"),
    [((1, None), False), ((0, None), True)],
)
async def test_skip_resolves_prior_defer_before_visibility_explicit_followup(
    mocker: MockerFixture,
    prior_ephemeral: bool,
    skip_result: tuple[int, Track | None],
    expected_ephemeral: bool,
) -> None:
    state: dict[str, bool | None] = {"original_ephemeral": prior_ephemeral}
    emitted_visibility: list[bool] = []

    async def delete_original_response() -> None:
        state["original_ephemeral"] = None

    async def send(_content: str, *, ephemeral: bool, **_kwargs: object) -> None:
        assert state["original_ephemeral"] is None
        emitted_visibility.append(ephemeral)

    response = SimpleNamespace(
        is_done=mocker.Mock(return_value=True),
        defer=mocker.AsyncMock(),
        send_message=mocker.AsyncMock(),
    )
    followup = SimpleNamespace(send=mocker.AsyncMock(side_effect=send))
    player = SimpleNamespace(
        is_playing=mocker.Mock(return_value=True),
        is_paused=False,
        skip_tracks=mocker.AsyncMock(return_value=skip_result),
    )
    context = SimpleNamespace(
        player=player,
        interaction=SimpleNamespace(
            response=response,
            followup=followup,
            delete_original_response=mocker.AsyncMock(
                side_effect=delete_original_response
            ),
        ),
        author=mocker.Mock(),
    )

    await inspect.unwrap(Music.skip.callback)(Music(mocker.Mock()), context)

    response.defer.assert_not_awaited()
    context.interaction.delete_original_response.assert_awaited_once_with()
    assert emitted_visibility == [expected_ephemeral]


@pytest.mark.asyncio
@pytest.mark.parametrize("selection_error", [None, RuntimeError("selection failed")])
async def test_search_selection_defers_before_slow_callback_and_edits_original(
    mocker: MockerFixture, selection_error: RuntimeError | None
) -> None:
    acknowledged = asyncio.Event()
    selection_started = asyncio.Event()
    release_selection = asyncio.Event()

    async def defer() -> None:
        acknowledged.set()

    async def on_select(_result: SearchResult) -> None:
        selection_started.set()
        await release_selection.wait()
        if selection_error is not None:
            raise selection_error

    response = SimpleNamespace(
        defer=mocker.AsyncMock(side_effect=defer),
        send_message=mocker.AsyncMock(),
        edit_message=mocker.AsyncMock(),
    )
    interaction = SimpleNamespace(
        response=response,
        edit_original_response=mocker.AsyncMock(),
    )
    result = SearchResult(title="Result", url="https://result")
    view = SearchResultsView([result], on_select)
    button = view.children[0]

    task = asyncio.create_task(button.callback(interaction))
    await selection_started.wait()

    assert acknowledged.is_set()
    response.defer.assert_awaited_once_with()
    response.send_message.assert_not_awaited()
    response.edit_message.assert_not_awaited()

    release_selection.set()
    if selection_error is None:
        await task
        interaction.edit_original_response.assert_awaited_once_with(view=view)
        assert button.disabled is True
    else:
        with pytest.raises(RuntimeError, match="selection failed"):
            await task
        interaction.edit_original_response.assert_not_awaited()

    response.send_message.assert_not_awaited()
    response.edit_message.assert_not_awaited()
