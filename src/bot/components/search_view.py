from collections.abc import Awaitable, Callable
from typing import cast

import discord
from discord.ui import Button, View
from loguru import logger

from src.bot.models import SearchResult


class SearchResultsView(View):
    """Display search results with selection buttons."""

    def __init__(
        self,
        results: list[SearchResult],
        on_select: Callable[[SearchResult], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=60)
        self.results = results
        self.on_select = on_select
        self._selected = False

        # Add numbered buttons for each result (max 5 due to Discord's button limit)
        for idx in range(min(len(results), 5)):
            self.add_item(_SearchResultButton(idx))

    async def _select(self, interaction: discord.Interaction, index: int) -> None:
        """Acknowledge and process a search result selection."""
        if self._selected:
            await interaction.response.defer()
            return

        self._selected = True
        for item in self.children:
            if isinstance(item, Button):
                item.disabled = True

        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        result = self.results[index]
        try:
            await self.on_select(result)
        except Exception:
            logger.exception("Search result selection failed")
            await interaction.edit_original_response(
                content="An error occurred while processing the selected track.",
                view=self,
            )
        finally:
            self.stop()

    def get_content(self) -> str:
        """Format search results as a numbered list."""
        if not self.results:
            return "No search results found."

        header = "Search Results:\n"
        lines = []
        for idx, result in enumerate(self.results[:5], start=1):
            # Format duration as MM:SS
            minutes = result.duration // 60
            seconds = result.duration % 60
            duration_str = f"{minutes}:{seconds:02d}"

            # Format: "1. title - author, duration"
            author = result.author_name or "Unknown"
            lines.append(f"{idx}. {result.title} - {author}, {duration_str}")

        lines_joined = f"```{'\n'.join(lines)}```"
        return "\n".join([header, lines_joined])

    def get_embed(self) -> discord.Embed:
        """Format search results as an embed."""
        embed = discord.Embed(title="Search Results", color=discord.Color.red())
        if not self.results:
            embed.description = "No search results found."
            return embed

        lines = []
        for idx, result in enumerate(self.results[:5], start=1):
            # Format duration as MM:SS
            minutes = result.duration // 60
            seconds = result.duration % 60
            duration_str = f"{minutes}:{seconds:02d}"

            # Format: "1. title - author, duration"
            author = result.author_name or "Unknown"
            lines.append(f"{idx}. {result.title} - {author}, {duration_str}")

        embed.description = "\n".join(lines)
        return embed


class _SearchResultButton(Button["SearchResultsView"]):
    """A typed search result button with a standard Discord callback."""

    def __init__(self, index: int) -> None:
        super().__init__(
            label=str(index + 1),
            style=discord.ButtonStyle.blurple,
            custom_id=f"select_{index}",
            row=0,
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        view = cast(SearchResultsView, self.view)
        await view._select(interaction, self.index)
