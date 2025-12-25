from collections.abc import Awaitable, Callable

import discord
from discord.ui import Button, View


class PaginatedView(View):
    def __init__(
        self,
        title: str,
        pages: list[str],
        on_update: Callable[[], Awaitable[tuple[str, list[str]]]],
    ) -> None:
        super().__init__(timeout=60)
        self.title = title
        self.pages = pages
        self.current_page = 0
        self.on_update = on_update

    def get_content(self) -> str:
        if not self.pages:
            return f"\n{self.title}\n```Queue is empty```"
        return f"\n{self.title}\n```{self.pages[self.current_page]}```"

    @discord.ui.button(label="Previous page", style=discord.ButtonStyle.gray)
    async def previous_button(
        self, interaction: discord.Interaction, button: Button
    ) -> None:
        self.current_page = max(0, self.current_page - 1)
        await interaction.response.edit_message(content=self.get_content(), view=self)

    @discord.ui.button(label="Update", style=discord.ButtonStyle.blurple)
    async def update_button(
        self, interaction: discord.Interaction, button: Button
    ) -> None:
        self.title, self.pages = await self.on_update()
        self.current_page = min(self.current_page, len(self.pages) - 1)
        await interaction.response.edit_message(content=self.get_content(), view=self)

    @discord.ui.button(label="Next page", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: Button
    ) -> None:
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        await interaction.response.edit_message(content=self.get_content(), view=self)
