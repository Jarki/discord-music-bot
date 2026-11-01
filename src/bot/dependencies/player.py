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
        self._current_track: Track | None = None
        self._current_voice_client: discord.VoiceClient | None = None
        self._generation = 0
        self._request_epoch = 0
        self._playback_lock = asyncio.Lock()

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

    def _get_voice_client_if_connected(self) -> discord.VoiceClient | None:
        """Return the voice client, treating a concurrent disconnect as absent."""
        try:
            return self._get_voice_client()
        except exc.NoVoiceChannelError:
            return None

    async def add_track(self, track: Track) -> Track:
        """Add a track to this guild's queue.

        Args:
            track: The track to add

        Returns:
            The added track with generated ID
        """
        return self.queue_manager.queue_item(self.guild_id, track)

    @staticmethod
    def _cleanup_source(source: discord.AudioSource) -> None:
        """Release resources held by an audio source that will not be played."""
        try:
            source.cleanup()
        except Exception as error:
            logger.warning(f"Error cleaning up rejected audio source: {error}")

    async def _play_track(
        self,
        track: Track,
        voice_client: discord.VoiceClient,
        generation: int,
    ) -> Track | None:
        """Resolve and play a track if its playback request is still current."""
        source: discord.AudioSource | None = None
        try:
            source = await YTDLSource.stream_from_url(track.url, loop=self.bot.loop)
            if (
                generation != self._generation
                or self._current_track is not track
                or self._current_voice_client is not voice_client
                or self._get_voice_client_if_connected() is not voice_client
                or not voice_client.is_connected()
            ):
                self._cleanup_source(source)
                if generation == self._generation and self._current_track is track:
                    self._current_track = None
                    self._current_voice_client = None
                return None

            voice_client.play(
                source,
                after=lambda error: self._after_playback(
                    error, voice_client, generation
                ),
            )
            logger.info(f"Now playing in guild {self.guild_id}: {track.title}")
            return track
        except BaseException as error:
            if source is not None:
                self._cleanup_source(source)
            if generation == self._generation and self._current_track is track:
                self._current_track = None
                self._current_voice_client = None
            if isinstance(error, asyncio.CancelledError):
                raise
            logger.error(f"Error playing track in guild {self.guild_id}: {error}")
            return None

    def _advance_queue(self, force_skip: bool = False) -> Track | None:
        """Advance the queue cursor without playing the next track."""
        try:
            track = self.queue_manager.get_next(self.guild_id, force_skip=force_skip)
            return track
        except RuntimeError as e:
            logger.debug(f"Queue exhausted for guild {self.guild_id}: {e}")
            return None

    async def _start_track_locked(
        self,
        track: Track,
        voice_client: discord.VoiceClient,
        excluded_track_id: str | None = None,
    ) -> Track | None:
        """Start a selected track, advancing past failures without retrying entries."""
        attempted_track_ids = {excluded_track_id} if excluded_track_id else set()
        request_epoch = self._request_epoch

        while track.track_id not in attempted_track_ids:
            attempted_track_ids.add(track.track_id)
            self._generation += 1
            generation = self._generation
            self._current_track = track
            self._current_voice_client = voice_client
            started = await self._play_track(track, voice_client, generation)
            if started is not None:
                return started

            if (
                request_epoch != self._request_epoch
                or generation != self._generation
                or self._get_voice_client_if_connected() is not voice_client
                or not voice_client.is_connected()
            ):
                return None

            track = self._advance_queue(force_skip=True)
            if track is None:
                return None

        return None

    async def _start_next_locked(
        self,
        force_skip: bool = False,
        excluded_track_id: str | None = None,
    ) -> Track | None:
        """Advance and start playback while the caller holds the lifecycle lock."""
        voice_client = self._get_voice_client_if_connected()
        if not voice_client:
            logger.warning(f"No voice client for guild {self.guild_id}")
            return None

        track = self._advance_queue(force_skip=force_skip)
        if track is None:
            self._current_track = None
            self._current_voice_client = None
            return None

        return await self._start_track_locked(
            track,
            voice_client,
            excluded_track_id=excluded_track_id,
        )

    async def play_next(self) -> Track | None:
        """Start the next track unless playback is already active or loading."""
        request_epoch = self._request_epoch
        async with self._playback_lock:
            if request_epoch != self._request_epoch:
                return None
            voice_client = self._get_voice_client_if_connected()
            if self._current_track is not None:
                if (
                    self._current_voice_client is voice_client
                    and voice_client is not None
                    and voice_client.is_connected()
                ):
                    return self._current_track
                self._generation += 1
                self._current_track = None
                self._current_voice_client = None
            if voice_client is not None and (
                voice_client.is_playing() or voice_client.is_paused()
            ):
                return None
            return await self._start_next_locked()

    async def _advance_after_playback(
        self,
        voice_client: discord.VoiceClient,
        generation: int,
        failed: bool,
    ) -> None:
        """Advance only for the callback belonging to current playback."""
        async with self._playback_lock:
            if generation != self._generation:
                return
            if (
                self._get_voice_client_if_connected() is not voice_client
                or not voice_client.is_connected()
            ):
                self._current_track = None
                self._current_voice_client = None
                return
            excluded_track_id = (
                self._current_track.track_id
                if failed and self._current_track is not None
                else None
            )
            self._current_track = None
            self._current_voice_client = None
            await self._start_next_locked(
                force_skip=failed,
                excluded_track_id=excluded_track_id,
            )

    def _after_playback(
        self,
        error: Exception | None,
        voice_client: discord.VoiceClient,
        generation: int,
    ) -> None:
        """Schedule advancement for a completed playback generation."""
        if error:
            logger.error(f"Playback error in guild {self.guild_id}: {error}")
        asyncio.run_coroutine_threadsafe(
            self._advance_after_playback(
                voice_client,
                generation,
                failed=error is not None,
            ),
            self.bot.loop,
        )

    @property
    def is_paused(self) -> bool:
        """Return whether the connected voice client is currently paused."""
        voice_client = self._get_voice_client_if_connected()
        return (
            voice_client is not None
            and voice_client.is_connected()
            and voice_client.is_paused()
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

    def _stop_playback(self, invalidate_requests: bool) -> bool:
        """Invalidate current playback and optionally cancel queued requests."""
        if invalidate_requests:
            self._request_epoch += 1
        self._generation += 1
        self._current_track = None
        self._current_voice_client = None
        vc = self._get_voice_client_if_connected()
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            return True
        return False

    def stop(self) -> bool:
        """Invalidate pending requests and stop active or paused audio."""
        return self._stop_playback(invalidate_requests=True)

    async def skip_tracks(self, count: int) -> tuple[int, Track | None]:
        """Skip up to 256 tracks atomically and start the resulting queue entry."""
        if count <= 0:
            return 0, None
        if count > 256:
            raise ValueError("count must not exceed 256")

        request_epoch = self._request_epoch
        async with self._playback_lock:
            if request_epoch != self._request_epoch:
                return 0, None
            has_current = self._current_track is not None
            self._stop_playback(invalidate_requests=False)
            skipped = 0
            track = None
            for _ in range(count):
                track = self._advance_queue(force_skip=True)
                if track is None:
                    if has_current:
                        skipped += 1
                    break
                skipped += 1
                has_current = True

            if track is None:
                return skipped, None

            voice_client = self._get_voice_client_if_connected()
            if not voice_client:
                logger.warning(f"No voice client for guild {self.guild_id}")
                return skipped, None

            started = await self._start_track_locked(track, voice_client)
            return skipped, started

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
