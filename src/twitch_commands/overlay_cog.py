import os
import json
from twitchio.ext import commands
from backend.media_mapper import get_media_files
from backend.ws_server import broadcast_overlay_message

class OverlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        overlay_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../overlay"))
        self.media_map = get_media_files(overlay_dir)
        print(f"[OverlayCog] Loaded overlay commands: {list(self.media_map.keys())}")

    async def try_handle_overlay(self, message):
        content = message.content.strip().lower()
        entry = self.media_map.get(content)
        if entry:
            rel_path, duration, is_gif = entry
            url = f"http://localhost:8080/{rel_path}"
            msg = {
                "type": "image",
                "url": url,
                "duration": duration * 1000,
            }
            await broadcast_overlay_message(json.dumps(msg))
            return True  # Message was handled as overlay
        return False  # Not an overlay message

def prepare(bot):
    if not bot.get_cog("OverlayCog"):
        bot.add_cog(OverlayCog(bot))