from collections.abc import Callable
from functools import wraps
from typing import Any, cast
from urllib import parse

import discord
import pydantic
from discord import app_commands
from discord.ext import commands
from loguru import logger
from yt_dlp.utils import DownloadError, GeoRestrictedError

from src.bot import components, exc, utils
from src.bot.dependencies import YTDLSource, get_in_memory_queue_manager
from src.bot.dependencies.player import Player
from src.bot.dependencies.player_manager import PlayerManager
from src.bot.models.core import QueueMode, Track


class MusicPlayerContext(pydantic.BaseModel):
    interaction: discord.Interaction
    guild_id: str
    player_manager: PlayerManager
    player: Player
    author: discord.Member
    vc: discord.VoiceClient

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)


def ensure_music_player_context(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(
        self: Music, interaction: discord.Interaction, *args: Any, **kwargs: Any
    ) -> Any:
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command cannot be used in private messages.", ephemeral=True
            )
            return

        author = cast(discord.Member, interaction.user)
        vc = cast(discord.VoiceClient | None, interaction.guild.voice_client)

        if vc is None:
            if author.voice and author.voice.channel:
                vc = await author.voice.channel.connect()
            else:
                await interaction.response.send_message(
                    "❌ You are not connected to a voice channel.", ephemeral=True
                )
                return

        elif author.voice and vc.channel != author.voice.channel:
            await vc.move_to(author.voice.channel)

        if self.player_manager is None:
            raise RuntimeError("Player manager not initialized.")

        player = self.player_manager.get_or_create_player(str(interaction.guild.id))

        context = MusicPlayerContext(
            interaction=interaction,
            guild_id=str(interaction.guild.id),
            player_manager=self.player_manager,
            player=player,
            author=author,
            vc=vc,
        )

        return await func(self, context, *args, **kwargs)

    return wrapper


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.player_manager: PlayerManager | None = None

    async def cog_load(self) -> None:
        queue_manager = get_in_memory_queue_manager()
        self.player_manager = PlayerManager(queue_manager, self.bot)
        return await super().cog_load()

    async def cog_unload(self) -> None:
        if self.bot.voice_clients:
            for vc in self.bot.voice_clients:
                await vc.disconnect(force=True)
        return await super().cog_unload()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Called whenever ANY interaction is invoked"""
        if not interaction.guild:
            return

        logger.debug(
            f"Interaction '{interaction.command.name if interaction.command else 'unknown'}' "
            f"used in guild {interaction.guild.id} ({interaction.guild.name}) "
            f"by {interaction.user}"
        )

    @app_commands.command(name="join", description="Joins the voice channel")
    @ensure_music_player_context
    async def join(self, context: MusicPlayerContext) -> None:
        """Joins the voice channel"""
        await context.interaction.response.send_message(
            "Joined voice channel!", ephemeral=True
        )

    @app_commands.command(name="leave", description="Leaves the voice channel")
    @ensure_music_player_context
    async def leave(self, context: MusicPlayerContext) -> None:
        """Leaves the voice channel"""
        if context.interaction.guild and context.interaction.guild.voice_client:
            await context.interaction.guild.voice_client.disconnect(force=True)
            await context.interaction.response.send_message(
                "Left voice channel!", ephemeral=True
            )
        else:
            await context.interaction.response.send_message(
                "Not in a voice channel.", ephemeral=True
            )

    async def _queue_track_and_play_maybe(
        self,
        context: MusicPlayerContext,
        track: Track,
    ) -> None | Track:
        player = context.player

        # Add track to queue
        await player.add_track(track)

        # If nothing is playing, start playback
        if not player.is_playing() and not player.is_paused:
            started_track = await player.play_next()
            if not started_track:
                await context.interaction.followup.send(
                    content="Failed to start playback."
                )
                return None

        return track

    async def try_handle_get_track_info_from_yt_url(
        self,
        context: MusicPlayerContext,
        yt_url: str,
        position: int | None = None,
        total: int | None = None,
    ) -> Track | list | None:
        """Try to fetch track info and handle Download/Geo errors by notifying `context`.

        Returns the track info on success, or `None` on handled errors.
        """
        try:
            return await YTDLSource.get_tracks_info(yt_url, loop=self.bot.loop)
        except DownloadError as e:
            # yt-dlp sometimes wraps GeoRestrictedError inside a DownloadError's exc_info.
            if (
                e.exc_info
                and len(e.exc_info) > 1
                and isinstance(e.exc_info[1], GeoRestrictedError)
            ):
                if position is not None and total is not None:
                    await context.interaction.followup.send(
                        content=f"Track {position}/{total} from playlist is not available in your region."
                    )
                else:
                    await context.interaction.followup.send(
                        content="Track from playlist is not available in your region."
                    )
                return None
            logger.exception("DownloadError while fetching track info", exc_info=e)
            return None
        except GeoRestrictedError:
            if position is not None and total is not None:
                await context.interaction.followup.send(
                    content=f"Track {position}/{total} from playlist is not available in your region."
                )
            else:
                await context.interaction.followup.send(
                    content="Track from playlist is not available in your region."
                )
            return None

    @app_commands.command(name="play", description="Add a track to the queue and play")
    @app_commands.describe(song="URL or search term of the song to play")
    @ensure_music_player_context
    async def play(self, context: MusicPlayerContext, song: str) -> None:
        """Add a track to the queue and play if nothing is playing"""
        await context.interaction.response.defer(ephemeral=False)

        try:
            track_or_tracklist = await YTDLSource.get_tracks_info(
                song, loop=self.bot.loop
            )
            if isinstance(track_or_tracklist, Track):
                logger.debug(f"Single track URL: {track_or_tracklist.url}")
                played_track = await self._queue_track_and_play_maybe(
                    context, track_or_tracklist
                )
                if played_track is not None:
                    await context.interaction.followup.send(
                        content=f"Added to queue: {self._format_track_link(played_track)}",
                        embed=self._get_track_card(played_track),
                    )
            elif isinstance(track_or_tracklist, list):
                logger.debug(f"Playlist with {len(track_or_tracklist)} tracks")
                if len(track_or_tracklist) == 0:
                    await context.interaction.followup.send(
                        content="No tracks found in the playlist."
                    )
                    return
                if len(track_or_tracklist) > 100:
                    await context.interaction.followup.send(
                        content="Playlist is too large (over 100 tracks)."
                    )
                    return

                index = self._try_get_index_from_yt_url_playlist(song)
                logger.debug(f"Starting playlist from index: {index}")
                await context.interaction.followup.send(
                    content=f"Adding {len(track_or_tracklist)} tracks to the queue ({song})"
                )
                for i, pt in enumerate(track_or_tracklist[index:], start=index + 1):
                    logger.debug(f"Playlist track URL ({i}): {pt.yt_url}")
                    track_info = await self.try_handle_get_track_info_from_yt_url(
                        context, pt.yt_url, i, len(track_or_tracklist)
                    )
                    if not track_info:
                        continue
                    if isinstance(track_info, Track):
                        try:
                            played_track = await self._queue_track_and_play_maybe(
                                context, track_info
                            )
                        except exc.NoVoiceChannelError as e:
                            logger.error(
                                f"Error playing track from playlist: {type(e)} {e}",
                                exc_info=e,
                            )
                            await context.interaction.followup.send(
                                content="An error occurred while trying to play the track: "
                                "Bot is not connected to a voice channel."
                            )
                            return
                        if played_track is not None:
                            await context.interaction.followup.send(
                                content=(
                                    f"Queueing track {i} out of {len(track_or_tracklist)}: "
                                    f"{self._format_track_link(played_track)}"
                                ),
                                embed=self._get_track_card(played_track),
                            )

        except Exception as e:
            logger.error(f"Error loading/playing track: {type(e)} {e}", exc_info=e)
            logger.exception("Full exception:")
            await context.interaction.followup.send(
                content="An error occurred while processing the track."
            )

    @app_commands.command(name="skip", description="Skip the current track")
    @app_commands.describe(songs="Number of songs to skip (default 1)")
    @ensure_music_player_context
    async def skip(self, context: MusicPlayerContext, songs: int = 1) -> None:
        """Skip the current track or multiple tracks"""
        player = context.player
        if not player:
            await context.interaction.response.send_message(
                "No player active for this guild.", ephemeral=True
            )
            return

        if not player.is_playing() and not player.is_paused:
            await context.interaction.response.send_message(
                "Nothing is playing.", ephemeral=True
            )
            return

        skipped, track = await player.skip_tracks(songs)
        if skipped > 0:
            if track is not None:
                await context.interaction.response.send_message(
                    f"Skipped {skipped} track(s). Now playing: {self._format_track_link(track)}",
                    ephemeral=False,
                    embed=self._get_track_card(track),
                )
            else:
                await context.interaction.response.send_message(
                    f"Skipped {skipped} track(s). No more tracks in the queue.",
                    ephemeral=False,
                )
        else:
            await context.interaction.response.send_message(
                "Could not skip tracks.", ephemeral=True
            )

    @app_commands.command(name="pause", description="Pause the current track")
    @ensure_music_player_context
    async def pause(self, context: MusicPlayerContext) -> None:
        """Pause the current track"""
        player = context.player
        if not player:
            await context.interaction.response.send_message(
                "No player active for this guild.", ephemeral=True
            )
            return
        player.pause()
        await context.interaction.response.send_message(
            "Paused playback.", ephemeral=True
        )

    @app_commands.command(name="resume", description="Resume paused playback")
    @ensure_music_player_context
    async def resume(self, context: MusicPlayerContext) -> None:
        """Resume paused playback"""
        player = context.player
        if not player:
            await context.interaction.response.send_message(
                "No player active for this guild.", ephemeral=True
            )
            return
        player.resume()
        await context.interaction.response.send_message(
            "Resumed playback.", ephemeral=True
        )

    @app_commands.command(
        name="mode", description="Set the playback mode for the current guild's player"
    )
    @app_commands.describe(mode="Playback mode to set")
    @app_commands.choices(mode=QueueMode.choices())
    @ensure_music_player_context
    async def mode(self, context: MusicPlayerContext, mode: str) -> None:
        """Set the playback mode for the current guild's player"""
        try:
            player = context.player
            new_mode = QueueMode(mode)
            logger.debug(
                f"Setting playback mode to {new_mode} for guild {context.guild_id}"
            )
            player.set_mode(new_mode)
            await context.interaction.response.send_message(
                f"Set playback mode to {mode}.", ephemeral=True
            )
        except ValueError as e:
            await context.interaction.response.send_message(str(e), ephemeral=True)

    @app_commands.command(name="current", description="See the currently playing track")
    @ensure_music_player_context
    async def current(self, context: MusicPlayerContext) -> None:
        player = context.player
        if not player or not player.current_track:
            await context.interaction.response.send_message(
                "No track is currently playing.", ephemeral=True
            )
            return

        track = player.current_track
        embed = self._get_track_card(track)
        await context.interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="queue", description="Show the current queue")
    @ensure_music_player_context
    async def queue(self, context: MusicPlayerContext) -> None:
        player = context.player
        if not player:
            await context.interaction.response.send_message(
                "No player active for this guild.", ephemeral=True
            )
            return

        all_tracks = player.get_all()

        songs_per_page = 10

        async def refresh_queue() -> tuple[str, list[str]]:
            # Fetch fresh data
            all_tracks = player.get_all()
            pages = utils.tracks_to_pages(all_tracks, songs_per_page=songs_per_page)
            return f"Current Queue ({len(all_tracks)} songs)", pages

        pages = utils.tracks_to_pages(all_tracks, songs_per_page=songs_per_page)
        view = components.PaginatedView(
            title=f"Current Queue ({len(all_tracks)} songs)",
            pages=pages,
            on_update=refresh_queue,
        )
        await context.interaction.response.send_message(
            content=view.get_content(),
            ephemeral=True,
            view=view,
        )

    @app_commands.command(name="clear", description="Clear the current queue")
    @ensure_music_player_context
    async def clear(self, context: MusicPlayerContext) -> None:
        player = context.player
        if not player:
            await context.interaction.response.send_message(
                "No player active for this guild.", ephemeral=True
            )
            return

        player.clear_queue()
        await context.interaction.response.send_message(
            "Cleared the queue.", ephemeral=True
        )

    def _get_track_card(self, track: Track, error: bool = False) -> discord.Embed:
        """Build an embed from a `Track` model."""
        title = track.title
        url = track.url
        thumbnail_url = track.thumbnail_url
        author_name = track.author_name
        duration = track.duration or 0

        embed_title = title if url is None else f"[{title}]({url})"
        if error:
            embed_title = f"❌ ERROR while playing {embed_title}"
        embed = discord.Embed(
            description=f"**{embed_title}**",
            color=discord.Color.from_rgb(255, 0, 0),  # YouTube red
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        if author_name:
            embed.set_author(name=author_name)

        if duration:
            minutes, seconds = divmod(duration, 60)
            if embed.description is None:
                embed.description = ""
            embed.description += f"\n⏱️ `{minutes}:{seconds:02d}`"

        return embed

    def _format_track_link(self, track: Track) -> str:
        """Return a user-facing link for the track (markdown-style if URL present)."""
        url = getattr(track, "url", None)
        if url:
            return f"[{track.title}]({url})"
        yt_url = getattr(track, "yt_url", None)
        if yt_url:
            return str(yt_url)
        return track.title

    def _try_get_index_from_yt_url_playlist(self, yt_url: str) -> int:
        qd = parse.parse_qs(parse.urlparse(yt_url).query)
        index = qd.get("index", [])
        if len(index) > 0:
            try:
                return int(index[0]) - 1
            except ValueError:
                return 0
        return 0
