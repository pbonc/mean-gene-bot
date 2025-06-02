import os
import logging
from twitchio.ext import commands
from sfx_registry import SFXRegistry
from playsound import playsound

logger = logging.getLogger("SFXCog")

class SFXCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.registry = getattr(bot, "sfx_registry", None) or SFXRegistry()
        if not hasattr(self.registry, "file_commands"):
            self.registry.scan_and_register()

    async def try_handle_sfx(self, message):
        if message.echo:
            return False
        content = message.content.strip().split()[0].lower()
        if content.startswith("!") and content in self.registry.file_commands:
            sfx_path = self.registry.file_commands[content]
            try:
                playsound(sfx_path)
                logger.info(f"Played SFX '{content}' ({sfx_path}) for user {message.author.name}")
            except Exception as e:
                logger.error(f"ERROR playing SFX '{content}': {e}")
            return True
        return False

def prepare(bot):
    if not bot.get_cog("SFXCog"):
        bot.add_cog(SFXCog(bot))