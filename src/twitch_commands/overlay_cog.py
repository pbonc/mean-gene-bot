import logging
from twitchio.ext import commands

logger = logging.getLogger("overlay")

class OverlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Mapping of chat commands to overlay actions.
        self.overlay_commands = {
            "!meme3": "trigger_meme3",
            "!dar<3": "trigger_dar_heart",
            "!dar<32": "trigger_dar_double_heart",
            "!hop<3": "trigger_hop_heart",
            # Add more overlay commands and their actions here
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
            # Here you would trigger your actual overlay event, e.g. via websocket or HTTP
            # For demonstration, we'll just print/log:
            print(f"[OverlayCog] Trigger overlay: {overlay_action} (from {command})")
            # If you have a websocket server or HTTP endpoint, send the event here!
            # Example:
            # await self.bot.overlay_ws.send_json({"action": overlay_action, "user": message.author.name})
            return True

        return False

def prepare(bot):
    if not bot.get_cog("OverlayCog"):
        bot.add_cog(OverlayCog(bot))