"""Player manager for handling per-guild Player instances."""

from discord.ext import commands

from src.bot.dependencies.player import Player
from src.bot.dependencies.queue import QueueProtocol


class PlayerManager:
    """Manages Player instances per guild."""

    def __init__(self, queue_manager: QueueProtocol, bot: commands.Bot) -> None:
        """Initialize the player manager.

        Args:
            queue_manager: The queue manager instance (singleton)
            bot: The Discord bot instance
        """
        self.queue_manager = queue_manager
        self.bot = bot
        self._players: dict[str, Player] = {}

    def get_or_create_player(self, guild_id: str) -> Player:
        """Get existing player or create new one for a guild.

        Args:
            guild_id: The guild ID to get/create player for

        Returns:
            The Player instance for this guild
        """
        if guild_id not in self._players:
            self._players[guild_id] = Player(
                guild_id=guild_id,
                queue_manager=self.queue_manager,
                bot=self.bot,
            )
        return self._players[guild_id]

    def get_player(self, guild_id: str) -> Player | None:
        """Get existing player for a guild.

        Args:
            guild_id: The guild ID to get player for

        Returns:
            The Player instance if it exists, None otherwise
        """
        return self._players.get(guild_id)

    def remove_player(self, guild_id: str) -> None:
        """Remove a player instance for a guild.

        Args:
            guild_id: The guild ID to remove player for
        """
        if guild_id in self._players:
            del self._players[guild_id]
