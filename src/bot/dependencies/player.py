import asyncio
from typing import TYPE_CHECKING

import discord
from loguru import logger

from src.bot.dependencies.queue import QueueProtocol
from src.bot.dependencies.ytdlp import YTDLSource
from src.bot.models.core import Track

if TYPE_CHECKING:
    from discord.ext.commands import Bot


class Player:
    """Per-guild player managing playback lifecycle and queue interaction."""

    def __init__(self, guild_id: str, queue_manager: QueueProtocol, bot: Bot) -> None:
        """Initialize a player for a specific guild.

        Args:
            guild_id: The guild this player manages
            queue_manager: Shared queue manager instance
            bot: The Discord bot instance
        """
        self.guild_id = guild_id
        self.queue_manager = queue_manager
        self.bot = bot
        self._current_track: Track | None = None

    def _get_voice_client(self) -> discord.VoiceClient | None:
        """Get the voice client for this guild.

        Returns the bot's voice client if connected to this guild's voice channel.
        """
        guild = self.bot.get_guild(int(self.guild_id))
        if not guild:
            return None

        # guild.voice_client returns the VoiceClient if bot is connected to this guild
        vc = guild.voice_client
        if vc is None or isinstance(vc, discord.VoiceClient):
            return vc
        return None

    async def add_track(self, track: Track) -> Track:
        """Add a track to this guild's queue.

        Args:
            track: The track to add

        Returns:
            The added track with generated ID
        """
        return self.queue_manager.queue_item(self.guild_id, track)

    async def play_next(
        self, voice_client: discord.VoiceClient | None = None
    ) -> Track | None:
        """Play the next track in the queue.

        Args:
            voice_client: Optional voice client. If not provided, will fetch it.

        Returns:
            The track that started playing, or None if queue is empty
        """
        if voice_client is None:
            voice_client = self._get_voice_client()

        if not voice_client:
            logger.warning(f"No voice client for guild {self.guild_id}")
            return None

        try:
            track = self.queue_manager.get_next(self.guild_id)
        except RuntimeError as e:
            logger.debug(f"Queue exhausted for guild {self.guild_id}: {e}")
            self._current_track = None
            return None

        self._current_track = track

        try:
            source = await YTDLSource.stream_from_url(track.url, loop=self.bot.loop)
            voice_client.play(source, after=self._after_playback)
            logger.info(f"Now playing in guild {self.guild_id}: {track.title}")
            return track
        except Exception as e:
            logger.error(f"Error playing track in guild {self.guild_id}: {e}")
            self._current_track = None
            return None

    def _after_playback(self, error: Exception | None) -> None:
        """Callback invoked when a track finishes playing.

        Args:
            error: Any error that occurred during playback
        """
        if error:
            logger.error(f"Playback error in guild {self.guild_id}: {error}")

        # Schedule next track on the event loop
        voice_client = self._get_voice_client()
        if voice_client and voice_client.is_connected():
            asyncio.run_coroutine_threadsafe(
                self.play_next(voice_client), self.bot.loop
            )

    @property
    def current_track(self) -> Track | None:
        """Get the currently playing track."""
        return self._current_track

    def is_playing(self) -> bool:
        """Check if this player is currently playing."""
        vc = self._get_voice_client()
        return vc is not None and vc.is_playing()

    def pause(self) -> bool:
        """Pause playback.

        Returns:
            True if paused successfully, False otherwise
        """
        vc = self._get_voice_client()
        if vc and vc.is_playing():
            vc.pause()
            return True
        return False

    def resume(self) -> bool:
        """Resume playback.

        Returns:
            True if resumed successfully, False otherwise
        """
        vc = self._get_voice_client()
        if vc and vc.is_paused():
            vc.resume()
            return True
        return False

    def stop(self) -> bool:
        """Stop playback.

        Returns:
            True if stopped successfully, False otherwise
        """
        vc = self._get_voice_client()
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            self._current_track = None
            return True
        return False
