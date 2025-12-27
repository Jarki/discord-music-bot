from collections.abc import Awaitable, Callable

import discord
from discord.ui import Button, View

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

        # Add numbered buttons for each result (max 5 due to Discord's button limit)
        for idx in range(min(len(results), 5)):
            button: Button = Button(
                label=str(idx + 1),
                style=discord.ButtonStyle.blurple,
                custom_id=f"select_{idx}",
                row=0,
            )
            # Store the index in the button for later retrieval
            button.custom_id = f"select_{idx}"
            button.callback = self._create_callback(idx)
            self.add_item(button)

    def _create_callback(
        self, index: int
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        """Create a callback function for a specific search result index."""

        async def callback(interaction: discord.Interaction) -> None:
            result = self.results[index]
            await self.on_select(result)
            # Disable all buttons after selection
            for item in self.children:
                if isinstance(item, Button):
                    item.disabled = True
            await interaction.response.edit_message(view=self)

        return callback

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
