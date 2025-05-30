import os
import random
import logging
from twitchio.ext import commands

logger = logging.getLogger("sfx")

class SFXCog(commands.Cog):
    def __init__(self, bot, sfx_registry):
        self.bot = bot
        self.sfx_registry = sfx_registry
        print(f"[SFXCog __init__] sfx_registry: {self.sfx_registry}")
        if self.sfx_registry:
            file_count = len(getattr(self.sfx_registry, "file_commands", {}))
            folder_count = len(getattr(self.sfx_registry, "folder_commands", {}))
            print(f"[SFXCog __init__] Loaded {file_count} file commands, {folder_count} folder commands")
        else:
            print("[SFXCog __init__] No sfx_registry provided!")

    async def try_handle_sfx(self, message):
        if message.echo:
            return False
        # Prevent the bot from responding to its own announcements (avoids recursion and double-responses)
        if message.author and message.author.name.lower() == self.bot.nick.lower():
            return False
        if not message.content.startswith("!"):
            return False

        cmd = message.content.split()[0]

        # SFX file command: play sound, no chat message
        if self.sfx_registry and cmd in getattr(self.sfx_registry, "file_commands", {}):
            sfx_path = os.path.join(self.sfx_registry.sfx_dir, self.sfx_registry.file_commands[cmd])
            try:
                from playsound import playsound
                playsound(sfx_path)
            except Exception as e:
                logger.error(f"Error playing SFX sound: {e}")
            return True  # SFX handled

        # SFX folder command: play random sound, announce the trigger command in chat
        if self.sfx_registry and cmd in getattr(self.sfx_registry, "folder_commands", {}):
            files = self.sfx_registry.folder_commands[cmd]
            if files:
                sfx_path = os.path.join(self.sfx_registry.sfx_dir, random.choice(files))
                file_cmd = f"!{os.path.splitext(os.path.basename(sfx_path))[0]}"
                try:
                    from playsound import playsound
                    playsound(sfx_path)
                except Exception as e:
                    logger.error(f"Error playing SFX sound: {e}")
                # Announce the trigger for the sound that was played
                await message.channel.send(file_cmd)
            return True  # SFX handled

        return False  # Not an SFX command

def prepare(bot):
    sfx_registry = getattr(bot, "sfx_registry", None)
    print(f"[SFXCog.prepare] sfx_registry: {sfx_registry}")
    if not bot.get_cog("SFXCog"):
        bot.add_cog(SFXCog(bot, sfx_registry))
        print("Loaded cog : SFXCog")
    else:
        print("SFXCog already loaded")