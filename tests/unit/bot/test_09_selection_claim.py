"""One-shot search result selection regressions for issue 09."""

import asyncio
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from src.bot.components.search_view import SearchResultsView
from src.bot.models import SearchResult


@pytest.mark.asyncio
async def test_overlapping_clicks_claim_before_defer_and_late_clicks_only_acknowledge(
    mocker: MockerFixture,
) -> None:
    release_first_defer = asyncio.Event()
    selection_started = asyncio.Event()
    release_selection = asyncio.Event()

    async def first_defer() -> None:
        await release_first_defer.wait()

    async def on_select(_result: SearchResult) -> None:
        selection_started.set()
        await release_selection.wait()

    result = SearchResult(title="Result", url="https://result")
    view = SearchResultsView([result], on_select)
    button = view.children[0]
    owner = SimpleNamespace(
        response=SimpleNamespace(defer=mocker.AsyncMock(side_effect=first_defer)),
        edit_original_response=mocker.AsyncMock(),
    )
    overlapping = SimpleNamespace(
        response=SimpleNamespace(defer=mocker.AsyncMock()),
        edit_original_response=mocker.AsyncMock(),
    )

    owner_task = asyncio.create_task(button.callback(owner))
    overlapping_task = asyncio.create_task(button.callback(overlapping))
    await asyncio.sleep(0)

    assert button.disabled is True
    assert view.is_finished()

    await overlapping_task
    overlapping.response.defer.assert_awaited_once_with()
    overlapping.edit_original_response.assert_not_awaited()
    assert not selection_started.is_set()

    release_first_defer.set()
    await selection_started.wait()

    while_running = SimpleNamespace(
        response=SimpleNamespace(defer=mocker.AsyncMock()),
        edit_original_response=mocker.AsyncMock(),
    )
    await button.callback(while_running)
    while_running.response.defer.assert_awaited_once_with()
    while_running.edit_original_response.assert_not_awaited()

    release_selection.set()
    await owner_task

    owner.response.defer.assert_awaited_once_with()
    owner.edit_original_response.assert_awaited_once_with(view=view)

    after_success = SimpleNamespace(
        response=SimpleNamespace(defer=mocker.AsyncMock()),
        edit_original_response=mocker.AsyncMock(),
    )
    await button.callback(after_success)
    after_success.response.defer.assert_awaited_once_with()
    after_success.edit_original_response.assert_not_awaited()


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
    owner.edit_original_response.assert_awaited_once_with(
        content="An error occurred while processing the selected track.",
        view=view,
    )
    assert button.disabled is True
    assert view.is_finished()
    assert selected_results == [result]
