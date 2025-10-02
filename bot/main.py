import os
import logging
from datetime import datetime
import importlib
import asyncio
from twitchio.ext import commands
from dotenv import load_dotenv
from bot.overlay_server import start_overlay_server, broadcast_overlay_message
from bot.weather_utils import fetch_weather, save_weather_message, get_random_weather_messages, get_any_weather_message

# Load .env file
load_dotenv()

TWITCH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_BOT_ID = os.getenv("TWITCH_BOT_ID")
TWITCH_CHANNELS = os.getenv("TWITCH_CHANNELS", "").split(",")

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.ERROR
)

class Bot(commands.Bot):
    @commands.command(name='afk')
    async def afk(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use this command.")
            return
        # Start AFK ticker task if not already running
        if not hasattr(self, '_afk_task') or self._afk_task is None or self._afk_task.done():
            self._afk_task = self.loop.create_task(self.afk_ticker_cycle_task())
            await ctx.send("AFK ticker started!")
        else:
            await ctx.send("AFK ticker is already running.")
    async def afk_ticker_cycle_task(self):
        import random
        from bot.twitch_stats import get_stream_info, get_sub_points
        from bot.labels_stats import get_ticker_messages
        while True:
            try:
                info = await get_stream_info()
                sub_points = await get_sub_points()
                label_messages = await get_ticker_messages()
                weather_msg = await get_any_weather_message()
                # Truncate uptime to minutes
                raw_uptime = info.get('uptime', 'N/A') if info else 'N/A'
                if raw_uptime and raw_uptime != 'N/A':
                    import re
                    match = re.match(r"(?:(\d+) days?, )?(\d+):(\d+):", raw_uptime)
                    if match:
                        days = int(match.group(1)) if match.group(1) else 0
                        hours = int(match.group(2)) if match.group(2) else 0
                        minutes = int(match.group(3)) if match.group(3) else 0
                        uptime_str = f"Uptime: {hours + days * 24}h {minutes}m"
                    else:
                        uptime_str = f"Uptime: {raw_uptime}"
                else:
                    uptime_str = "Uptime: N/A"
                # Read latest subscriber/follower from data/labels/
                workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                labels_dir = os.path.join(workspace_root, "bot", "data", "labels")
                latest_sub = "N/A"
                latest_follower = "N/A"
                try:
                    sub_path = os.path.join(labels_dir, "most_recent_resubscriber.txt")
                    if os.path.isfile(sub_path):
                        with open(sub_path, "r", encoding="utf-8") as f:
                            latest_sub = f.read().strip() or "N/A"
                except Exception:
                    pass
                try:
                    follower_path = os.path.join(labels_dir, "most_recent_follower.txt")
                    if os.path.isfile(follower_path):
                        with open(follower_path, "r", encoding="utf-8") as f:
                            latest_follower = f.read().strip() or "N/A"
                except Exception:
                    pass
                elements = [
                    f"Title: {info.get('title', 'N/A') if info else 'N/A'}",
                    f"Viewers: {info.get('viewers', 'N/A') if info else 'N/A'}",
                    uptime_str,
                    f"Latest Subscriber: {latest_sub}",
                    f"Latest Follower: {latest_follower}",
                    f"Followers: {info.get('followers', 'N/A') if info else 'N/A'}",
                    f"Sub Points: {sub_points if sub_points is not None else 'N/A'}"
                ] + label_messages
                if weather_msg:
                    if weather_msg.startswith("Weather: "):
                        elements.append(weather_msg[len("Weather: "):])
                    else:
                        elements.append(weather_msg)
                if elements:
                    msg = random.choice(elements)
                    await broadcast_overlay_message({"type": "afk_ticker", "message": msg})
                else:
                    await broadcast_overlay_message({"type": "afk_ticker", "message": "AFK: No data available."})
                await asyncio.sleep(0.25)
            except Exception as e:
                logging.error(f"[AFK TICKER ERROR] {e}", exc_info=True)
    async def ticker_cycle_task(self):
        from bot.twitch_stats import get_stream_info, get_recent_subscriber, get_sub_points
        from bot.labels_stats import get_ticker_messages
        while True:
            try:
                info = await get_stream_info()
                subscriber = await get_recent_subscriber()
                sub_points = await get_sub_points()
                label_messages = await get_ticker_messages()
                weather_msgs = await get_random_weather_messages(5)
                messages = [
                    f"Title: {info.get('title', 'N/A') if info else 'N/A'}",
                    f"Viewers: {info.get('viewers', 'N/A') if info else 'N/A'}",
                    f"Uptime: {info.get('uptime', 'N/A') if info else 'N/A'}",
                    f"Recent Subscriber: {subscriber if subscriber else 'N/A'}",
                    f"Sub Points: {sub_points if sub_points is not None else 'N/A'}"
                ] + label_messages
                if weather_msgs:
                    for msg in weather_msgs:
                        if msg.startswith("Weather: "):
                            messages.append(msg[len("Weather: "):])
                        else:
                            messages.append(msg)
                for msg in messages:
                    await broadcast_overlay_message({"type": "ticker", "text": msg})
                    await asyncio.sleep(5)
            except Exception as e:
                logging.error(f"[TICKER ERROR] {e}", exc_info=True)
            await asyncio.sleep(1)
    @commands.command(name='ticker')
    async def ticker(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use this command.")
            return
        await broadcast_overlay_message({"type": "ticker", "text": "Mean Gene Bot connected (manual test)."})
        await ctx.send("Ticker message sent to overlay.")

    @commands.command(name="weather")
    async def weather_command(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use this command.")
            return
        parts = ctx.message.content.split(" ", 2)
        if len(parts) < 3 or parts[1] != "add":
            await ctx.send("Usage: !weather add <location>")
            return
        location = parts[2].strip()
        # Only save the location string, not the weather message
        if location:
            save_weather_message(location)
            await ctx.send(f"Location '{location}' added to weather ticker!")
        else:
            await ctx.send("Location not found or API error.")

    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            client_id=TWITCH_CLIENT_ID,
            prefix="!",
            initial_channels=TWITCH_CHANNELS
        )

    async def event_ready(self):
        print(f"Logged in as | {self.nick}")
        # Show overlay ticker message once, then revert
        await broadcast_overlay_message({"type": "ticker", "text": "Mean Gene Bot connected."})
        await asyncio.sleep(4)  # Show for 4 seconds
        await broadcast_overlay_message({"type": "ticker", "text": "Welcome to the Darmunist News Network."})

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

    # Start ticker cycle tasks
    ticker_task = asyncio.create_task(bot.ticker_cycle_task())
    afk_ticker_task = asyncio.create_task(bot.afk_ticker_cycle_task())

    # Automatically load all cogs in bot/commands/
    commands_dir = os.path.join(os.path.dirname(__file__), "commands")
    if os.path.isdir(commands_dir):
        for filename in os.listdir(commands_dir):
            if filename.endswith(".py") and filename not in ("__init__.py", "base_command.py"):
                modulename = f"bot.commands.{filename[:-3]}"
                module = importlib.import_module(modulename)
                if hasattr(module, "prepare"):
                    module.prepare(bot)
    # Load modnews cog
    from bot.commands.modnews import prepare as modnews_prepare
    modnews_prepare(bot)

    # Run the bot (this blocks until shutdown)
    await bot.start()
    # Optionally, wait for overlay and ticker tasks to finish (if bot exits first)
    await overlay_task
    await ticker_task

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"[BOT FATAL ERROR] {e}", exc_info=True)