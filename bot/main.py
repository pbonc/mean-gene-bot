import os
import importlib
import asyncio
from twitchio.ext import commands
from dotenv import load_dotenv
from bot.overlay_server import start_overlay_server, broadcast_overlay_message

# Load .env file
load_dotenv()

TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_BOT_ID = os.getenv("TWITCH_BOT_ID")
TWITCH_CHANNELS = os.getenv("TWITCH_CHANNELS", "").split(",")

class Bot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            client_id=TWITCH_CLIENT_ID,
            prefix="!",
            initial_channels=TWITCH_CHANNELS
        )

    async def event_ready(self):
        print(f"Logged in as | {self.nick}")

    async def event_message(self, message):
        author_name = message.author.name if message.author else "Unknown"
        print(f"Message from {author_name}: {message.content}")
        if message.author:
            await self.handle_commands(message)

    @commands.command(name='hello')
    async def hello(self, ctx):
        await ctx.send(f"Hello, {ctx.author.name}!")

    # Example overlay command for you to adjust
    @commands.command(name='overlaytest')
    async def overlaytest(self, ctx):
        # This will display the test image on the overlay
        await broadcast_overlay_message({"image": "/gifs/darheart2.jpg"})
        await ctx.send("Overlay image triggered!")

async def main():
    # Start the overlay server in the background
    overlay_task = asyncio.create_task(start_overlay_server())
    # Create and start the bot
    bot = Bot()

    # Automatically load all cogs in bot/commands/
    commands_dir = os.path.join(os.path.dirname(__file__), "commands")
    if os.path.isdir(commands_dir):
        for filename in os.listdir(commands_dir):
            if filename.endswith(".py") and filename not in ("__init__.py", "base_command.py"):
                modulename = f"bot.commands.{filename[:-3]}"
                module = importlib.import_module(modulename)
                if hasattr(module, "prepare"):
                    module.prepare(bot)

    # Run the bot (this blocks until shutdown)
    await bot.start()
    # Optionally, wait for overlay task to finish (if bot exits first)
    await overlay_task

if __name__ == "__main__":
    asyncio.run(main())