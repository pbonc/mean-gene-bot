import os
import asyncio
from twitchio.ext import commands
from sfx_registry import SFXRegistry
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.ws_server import broadcast_overlay_message

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
        if content in self.registry.file_commands:
            sfx_path = self.registry.file_commands[content]
            payload = {
                "type": "play_sfx",
                "sfx_path": sfx_path
            }
            await broadcast_overlay_message(payload)
            print(f"[SFXCog] Played SFX '{content}' ({sfx_path}) for user {message.author.name}")
            return True
        return False

def prepare(bot):
    if not bot.get_cog("SFXCog"):
        bot.add_cog(SFXCog(bot))