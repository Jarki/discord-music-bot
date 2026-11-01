"""Regression coverage for search result shaping and command responses."""

import inspect
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_mock import MockerFixture

from src.bot.client import Music
from src.bot.components import SearchResultsView
from src.bot.dependencies.ytdlp import YTDLSource
from src.bot.models import SearchResult

pytestmark = pytest.mark.asyncio


def _context(mocker: MockerFixture) -> SimpleNamespace:
    return SimpleNamespace(
        interaction=SimpleNamespace(
            response=SimpleNamespace(
                defer=mocker.AsyncMock(), is_done=mocker.Mock(return_value=False)
            ),
            followup=SimpleNamespace(send=mocker.AsyncMock()),
        )
    )


async def test_play_replies_when_search_or_playlist_is_empty(
    mocker: MockerFixture,
) -> None:
    mocker.patch("src.bot.client.YTDLSource.get_tracks_info", return_value=[])
    context = _context(mocker)
    music = Music(mocker.Mock())

    await inspect.unwrap(Music.play.callback)(music, context, "no matches")

    context.interaction.followup.send.assert_awaited_once_with(
        content="No tracks found for this search or playlist.",
        ephemeral=True,
    )


@pytest.mark.parametrize("result_count", [1, 3])
async def test_play_presents_search_results_and_forwards_selection(
    mocker: MockerFixture, result_count: int
) -> None:
    results = [
        SearchResult(
            title=f"Result {index}",
            url=f"https://www.youtube.com/watch?v=result{index}",
            author_name="Artist",
            duration=60 + index,
        )
        for index in range(result_count)
    ]
    mocker.patch("src.bot.client.YTDLSource.get_tracks_info", return_value=results)
    context = _context(mocker)
    music = Music(mocker.Mock())
    handle_selection = mocker.patch.object(
        music, "_handle_search_result_selection", new=mocker.AsyncMock()
    )

    await inspect.unwrap(Music.play.callback)(music, context, "matching query")

    context.interaction.followup.send.assert_awaited_once()
    send_kwargs = context.interaction.followup.send.await_args.kwargs
    view = send_kwargs["view"]
    assert isinstance(view, SearchResultsView)
    assert view.results == results
    assert send_kwargs["embed"].description is not None
    assert all(result.title in send_kwargs["embed"].description for result in results)
    assert send_kwargs["ephemeral"] is True

    selected = results[-1]
    await view.on_select(selected)
    handle_selection.assert_awaited_once_with(context, selected)


async def test_single_search_entry_is_list_and_keeps_stable_page_url(
    mocker: MockerFixture,
) -> None:
    page_url = "https://www.youtube.com/watch?v=stable"

    def entries() -> Iterator[dict[str, Any] | None]:
        yield None
        yield {
            "title": "Only result",
            "webpage_url": page_url,
            "url": "https://media.example/audio?expires=300",
        }

    mocker.patch(
        "src.bot.dependencies.ytdlp.ytdl.extract_info",
        return_value={"extractor": "youtube:search", "entries": entries()},
    )

    results = await YTDLSource.get_tracks_info("only result")

    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert results[0].url == page_url
