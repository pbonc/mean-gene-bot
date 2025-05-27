import os
import random
import logging
from twitchio.ext import commands

logger = logging.getLogger("sfx")

class SFXCog(commands.Cog):
    def __init__(self, bot, sfx_registry):
        self.bot = bot
        self.sfx_registry = sfx_registry

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo or not message.content.startswith("!"):
            # Let other cogs or TwitchIO handle commands/events
            return

        cmd = message.content.split()[0]

        # SFX file command: play sound, no chat message
        if self.sfx_registry and cmd in getattr(self.sfx_registry, "file_commands", {}):
            sfx_path = os.path.join("sfx", self.sfx_registry.file_commands[cmd])
            try:
                from playsound import playsound
                playsound(sfx_path)
            except Exception as e:
                logger.error(f"Error playing SFX sound: {e}")
            return

        # SFX folder command: play random sound, send trigger command in chat
        if self.sfx_registry and cmd in getattr(self.sfx_registry, "folder_commands", {}):
            files = self.sfx_registry.folder_commands[cmd]
            if files:
                sfx_path = os.path.join("sfx", random.choice(files))
                file_cmd = f"!{os.path.splitext(os.path.basename(sfx_path))[0]}"
                try:
                    from playsound import playsound
                    playsound(sfx_path)
                except Exception as e:
                    logger.error(f"Error playing SFX sound: {e}")
                await message.channel.send(file_cmd)
            return

def prepare(bot):
    sfx_registry = getattr(bot, "sfx_registry", None)
    # Prevent double-loading
    if not bot.get_cog("SFXCog"):
        bot.add_cog(SFXCog(bot, sfx_registry))