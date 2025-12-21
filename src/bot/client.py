from typing import cast

import discord
from discord.ext import commands
from loguru import logger

from src.bot.dependencies import YTDLSource, get_in_memory_queue_manager
from src.bot.dependencies.player_manager import PlayerManager
from src.bot.models.core import Track


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
    async def on_command(self, ctx: commands.Context) -> None:
        """Called whenever ANY command is invoked"""
        if not ctx.guild:
            return

        logger.debug(
            f"Command '{ctx.command}' used in guild {ctx.guild.id} "
            f"({ctx.guild.name}) by {ctx.author}"
        )

    @commands.command()
    @commands.guild_only()
    async def join(self, ctx: commands.Context) -> None:
        """Joins the voice channel"""
        pass  # Handled in ensure_voice_and_player

    @commands.command()
    @commands.guild_only()
    async def leave(self, ctx: commands.Context) -> None:
        """Leaves the voice channel"""
        if ctx.voice_client:
            await ctx.voice_client.disconnect(force=True)

    @commands.command()
    @commands.guild_only()
    async def playi(self, ctx: commands.Context, url: str) -> None:
        """Add a track to the queue and play if nothing is playing"""
        vc = cast(discord.VoiceClient, ctx.voice_client)
        player_manager = cast(PlayerManager, self.player_manager)
        guild = cast(discord.Guild, ctx.guild)

        msg = await ctx.send("Loading your track...")
        try:
            track = await YTDLSource.get_track_info(url, loop=self.bot.loop)
            logger.debug(f"Used extractor {track.type} for URL: {url}")

            # Get player for this guild
            player = player_manager.get_or_create_player(str(guild.id))

            # Add track to queue
            await player.add_track(track)

            # If nothing is playing, start playback
            if not player.is_playing():
                started_track = await player.play_next(vc)
                if started_track:
                    await msg.edit(
                        content=f"Now playing: {started_track.title}",
                        embed=self._get_track_card(started_track),
                    )
                else:
                    await msg.edit(content="Failed to start playback.")
            else:
                await msg.edit(
                    content=f"Added to queue: {track.title}",
                    embed=self._get_track_card(track),
                )
        except Exception as e:
            logger.error(f"Error loading/playing track: {e}", exc_info=e)
            await msg.edit(content="An error occurred while processing the track.")

    @commands.command()
    @commands.guild_only()
    async def skip(self, ctx: commands.Context) -> None:
        """Skip the current track"""
        if not ctx.guild or not self.player_manager:
            return

        player = self.player_manager.get_player(str(ctx.guild.id))
        if not player:
            await ctx.send("No player active for this guild.")
            return

        if player.stop():
            # The after callback will automatically play the next track
            await ctx.send("Skipped current track.")
        else:
            await ctx.send("Nothing is playing.")

    @commands.command()
    @commands.guild_only()
    async def pause(self, ctx: commands.Context) -> None:
        """Stops and disconnects the bot from voice"""
        vc = cast(discord.VoiceClient, ctx.voice_client)
        vc.pause()

    @commands.command()
    @commands.guild_only()
    async def resume(self, ctx: commands.Context) -> None:
        """Resumes paused playback"""
        vc = cast(discord.VoiceClient, ctx.voice_client)
        vc.resume()

    @playi.before_invoke
    @skip.before_invoke
    @pause.before_invoke
    @resume.before_invoke
    @join.before_invoke
    async def ensure_voice_and_player(self, ctx: commands.Context) -> None:
        """Ensure bot is in voice channel before playing"""
        author = cast(discord.Member, ctx.author)
        vc = cast(discord.VoiceClient | None, ctx.voice_client)
        assert vc is None or isinstance(vc, discord.VoiceClient)

        if vc is None:
            if author.voice and author.voice.channel:
                await author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif author.voice and vc.channel != author.voice.channel:
            await vc.move_to(author.voice.channel)

        if self.player_manager is None:
            raise RuntimeError("Player manager not initialized.")

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
