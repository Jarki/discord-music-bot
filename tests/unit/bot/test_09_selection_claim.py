"""One-shot search result selection regressions for issue 09."""

import asyncio
from types import SimpleNamespace

import pytest
from discord.ui.view import ViewStore
from pytest_mock import MockerFixture

from src.bot.components.search_view import SearchResultsView
from src.bot.models import SearchResult


@pytest.mark.asyncio
async def test_pending_selection_stays_routable_and_publishes_disabled_view_first(
    mocker: MockerFixture,
) -> None:
    selection_started = asyncio.Event()
    release_selection = asyncio.Event()
    duplicate_acknowledged = asyncio.Event()
    selected_results: list[SearchResult] = []

    async def on_select(result: SearchResult) -> None:
        selected_results.append(result)
        selection_started.set()
        await release_selection.wait()

    result = SearchResult(title="Result", url="https://result")
    view = SearchResultsView([result], on_select)
    button = view.children[0]
    store = ViewStore(mocker.Mock())
    store.add_view(view, message_id=42)

    owner = SimpleNamespace(
        message=SimpleNamespace(id=42),
        data={},
        response=SimpleNamespace(defer=mocker.AsyncMock()),
        edit_original_response=mocker.AsyncMock(),
    )

    async def acknowledge_duplicate() -> None:
        duplicate_acknowledged.set()

    duplicate = SimpleNamespace(
        message=SimpleNamespace(id=42),
        data={},
        response=SimpleNamespace(
            defer=mocker.AsyncMock(side_effect=acknowledge_duplicate)
        ),
        edit_original_response=mocker.AsyncMock(),
    )

    store.dispatch_view(button.type.value, button.custom_id, owner)
    await selection_started.wait()

    owner.response.defer.assert_awaited_once_with()
    owner.edit_original_response.assert_awaited_once_with(view=view)
    assert button.disabled is True
    assert view.is_dispatching()
    assert not view.is_finished()

    store.dispatch_view(button.type.value, button.custom_id, duplicate)
    await duplicate_acknowledged.wait()

    duplicate.response.defer.assert_awaited_once_with()
    duplicate.edit_original_response.assert_not_awaited()
    assert selected_results == [result]

    release_selection.set()
    await view.wait()

    assert view.is_finished()
    assert not view.is_dispatching()
    assert selected_results == [result]


@pytest.mark.asyncio
async def test_side_effect_then_failure_remains_claimed_and_shows_generic_error(
    mocker: MockerFixture,
) -> None:
    side_effect_done = asyncio.Event()
    release_failure = asyncio.Event()
    selected_results: list[SearchResult] = []

    async def on_select(result: SearchResult) -> None:
        selected_results.append(result)
        side_effect_done.set()
        await release_failure.wait()
        raise RuntimeError("private queue failure details")

    result = SearchResult(title="Result", url="https://result")
    view = SearchResultsView([result], on_select)
    button = view.children[0]
    owner = SimpleNamespace(
        response=SimpleNamespace(defer=mocker.AsyncMock()),
        edit_original_response=mocker.AsyncMock(),
    )
    late = SimpleNamespace(
        response=SimpleNamespace(defer=mocker.AsyncMock()),
        edit_original_response=mocker.AsyncMock(),
    )
    mocker.patch("src.bot.components.search_view.logger.exception")

    owner_task = asyncio.create_task(button.callback(owner))
    await side_effect_done.wait()
    await button.callback(late)

    late.response.defer.assert_awaited_once_with()
    late.edit_original_response.assert_not_awaited()
    assert selected_results == [result]

    release_failure.set()
    await owner_task

    owner.response.defer.assert_awaited_once_with()
    assert owner.edit_original_response.await_args_list == [
        mocker.call(view=view),
        mocker.call(
            content="An error occurred while processing the selected track.",
            view=view,
        ),
    ]
    assert button.disabled is True
    assert view.is_finished()
    assert selected_results == [result]
