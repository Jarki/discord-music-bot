import asyncio
from typing import TYPE_CHECKING

import discord
from loguru import logger

from src.bot import exc
from src.bot.dependencies.queue import QueueProtocol
from src.bot.dependencies.ytdlp import YTDLSource
from src.bot.models.core import QueueMode, Track

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
        self.is_paused = False
        self._current_track: Track | None = None

        self._autoplay = True

    def _get_voice_client(self) -> discord.VoiceClient | None:
        """Get the voice client for this guild.

        Returns the bot's voice client if connected to this guild's voice channel.
        """
        guild = self.bot.get_guild(int(self.guild_id))
        if not guild:
            return None

        # guild.voice_client returns the VoiceClient if bot is connected to this guild
        vc = guild.voice_client
        if isinstance(vc, discord.VoiceClient):
            return vc
        raise exc.NoVoiceChannelError(
            f"Bot is not connected to a voice channel in guild {self.guild_id}"
        )

    async def add_track(self, track: Track) -> Track:
        """Add a track to this guild's queue.

        Args:
            track: The track to add

        Returns:
            The added track with generated ID
        """
        return self.queue_manager.queue_item(self.guild_id, track)

    async def _play_track(self, track: Track) -> Track | None:
        """Play a specific track immediately.

        Args:
            track: The track to play
        """
        voice_client = self._get_voice_client()
        if not voice_client:
            logger.warning(f"No voice client for guild {self.guild_id}")
            return None

        try:
            source = await YTDLSource.stream_from_url(track.url, loop=self.bot.loop)
            voice_client.play(source, after=self._after_playback)
            logger.info(f"Now playing in guild {self.guild_id}: {track.title}")
            return track
        except Exception as e:
            logger.error(f"Error playing track in guild {self.guild_id}: {e}")
            self._current_track = None
            return None

    def _advance_queue(self, force_skip: bool = False) -> Track | None:
        """Advance the queue cursor without playing the next track."""
        try:
            track = self.queue_manager.get_next(self.guild_id, force_skip=force_skip)
            return track
        except RuntimeError as e:
            logger.debug(f"Queue exhausted for guild {self.guild_id}: {e}")
            return None

    async def _autoplay_next(self) -> None:
        """Automatically play the next track based on autoplay logic."""
        if not self._autoplay:
            self._autoplay = True
            return

        voice_client = self._get_voice_client()
        if not voice_client:
            logger.warning(f"No voice client for guild {self.guild_id}")
            return

        track = self._advance_queue()
        self._current_track = track
        if track is not None:
            await self._play_track(track)

    async def play_next(self) -> Track | None:
        """Play the next track in the queue.

        Returns:
            The track that started playing, or None if queue is empty
        """
        voice_client = self._get_voice_client()
        if not voice_client:
            logger.warning(f"No voice client for guild {self.guild_id}")
            return None

        track = self._advance_queue()
        self._current_track = track

        if self._current_track is not None:
            await self._play_track(self._current_track)

        return self._current_track

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
            asyncio.run_coroutine_threadsafe(self._autoplay_next(), self.bot.loop)

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
            self.is_paused = True
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
            self.is_paused = False
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

    async def skip_tracks(self, count: int) -> tuple[int, Track | None]:
        """Skip multiple tracks in the queue and start playing the next one.

        Args:
            count: Number of tracks to skip (must be >= 1)

        Returns:
            Number of tracks actually skipped
        """
        if count <= 0:
            return 0, None

        # Advance cursor count times
        skipped = 0
        track = None
        for _ in range(count):
            track = self._advance_queue(force_skip=True)
            if track is not None:
                skipped += 1

        self._current_track = track
        self._autoplay = False
        if track is not None:
            self.stop()
            await self._play_track(track)

        if track is None:
            self.stop()
            self._current_track = None

        return skipped, self._current_track

    def set_mode(self, mode: QueueMode) -> None:
        """Set the playback mode for this player's queue.

        Args:
            mode: The playback mode to set
        """
        self.queue_manager.set_mode(self.guild_id, mode)

    def get_all(self) -> list[Track]:
        """Get all tracks in this player's queue.

        Returns:
            List of all tracks in the queue
        """
        return self.queue_manager.get_all_items(self.guild_id)

    def clear_queue(self) -> None:
        """Clear all tracks from this player's queue."""
        self.queue_manager.reset_queue(self.guild_id)
        self.stop()
