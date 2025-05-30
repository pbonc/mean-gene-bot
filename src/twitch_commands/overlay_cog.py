import os
import json
from twitchio.ext import commands
from backend.media_mapper import get_media_files
from backend.ws_server import broadcast_overlay_message

class OverlayCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        # Path to overlay directory (adjust as needed)
        overlay_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../overlay"))
        self.media_map = get_media_files(overlay_dir)

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

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
            # Don't call handle_commands for overlay triggers.
            return

        # Only call for non-overlay messages
        await self.bot.handle_commands(message)