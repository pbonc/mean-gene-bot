import logging
from twitchio.ext import commands
import asyncio
import json

# Import your broadcast function from the websocket server module
from backend.ws_server import broadcast_overlay_message

logger = logging.getLogger("overlay")

class OverlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.overlay_commands = {
            "!meme3": "trigger_meme3",
            "!dar<3": "trigger_dar_heart",
            "!dar<32": "trigger_dar_double_heart",
            "!hop<3": "trigger_hop_heart",
        }
        logger.info(f"[OverlayCog] Loaded overlay commands: {list(self.overlay_commands.keys())}")

    async def try_handle_overlay(self, message):
        print(f"[OverlayCog] try_handle_overlay called with: {message.content}")
        if message.echo:
            return False
        if message.author and message.author.name.lower() == self.bot.nick.lower():
            return False
        if not message.content.startswith("!"):
            return False

        command = message.content.split()[0]
        if command in self.overlay_commands:
            overlay_action = self.overlay_commands[command]
            logger.info(f"[OverlayCog] Handling overlay command: {command} -> {overlay_action}")
            print(f"[OverlayCog] Trigger overlay: {overlay_action} (from {command})")
            
            # Broadcast overlay action to all connected overlay clients
            payload = {
                "action": overlay_action,
                "user": message.author.name
            }
            # If your overlay websocket runs in a separate event loop/thread, use this:
            if hasattr(self.bot, "overlay_ws_loop") and self.bot.overlay_ws_loop is not asyncio.get_event_loop():
                # Use thread-safe coroutine execution
                asyncio.run_coroutine_threadsafe(
                    broadcast_overlay_message(payload),
                    self.bot.overlay_ws_loop
                )
            else:
                # Normal case: same event loop
                await broadcast_overlay_message(payload)

            return True

        return False

def prepare(bot):
    if not bot.get_cog("OverlayCog"):
        bot.add_cog(OverlayCog(bot))