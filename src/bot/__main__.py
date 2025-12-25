# This example requires the 'members' and 'message_content' privileged intents to function.


import discord
from discord.ext import commands
from loguru import logger

from src.bot.client import Music
from src.logger_config import setup_logger
from src.shared.models.config import Settings


async def main() -> None:
    setup_logger()

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix="/", intents=intents)

    @bot.event
    async def setup_hook() -> None:
        """Called when the bot is starting up"""
        await bot.add_cog(Music(bot))
        # Sync the command tree to register slash commands with Discord
        await bot.tree.sync()
        logger.info("Command tree synced")

    @bot.event
    async def on_ready() -> None:
        # Tell the type checker that User is filled up at this point
        assert bot.user is not None

        logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    token = Settings().discord_token  # type: ignore
    try:
        await bot.start(token)
    finally:
        await asyncio.wait_for(bot.close(), timeout=10.0)
        logger.info("Bot has exited.")


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrupted and shutting down.")
