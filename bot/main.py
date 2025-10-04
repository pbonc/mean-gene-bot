import shutil
import signal
def backup_raffle_state():
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raffle_state.json")
    if os.path.isfile(src):
        from datetime import datetime
        backup_dir = os.path.join(os.path.dirname(src), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(backup_dir, f"raffle_state_backup_{timestamp}.json")
        shutil.copy2(src, dst)
        print(f"[RAFFLE BACKUP] Backed up raffle_state.json to {dst}")
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

    # Track last AI usage per user (username: datetime)
    _ai_cooldowns = {}


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
        from bot.labels_stats import get_ticker_messages, get_raffle_odds_message, get_raffle_encouragement
        while True:
            try:
                info = await get_stream_info()
                sub_points = await get_sub_points()
                raffle_odds = await get_raffle_odds_message()
                raffle_enc = await get_raffle_encouragement()
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
                # Build core info (ordered, no duplicates)
                core_messages = [
                    f"Title: {info.get('title', 'N/A') if info else 'N/A'}",
                    raffle_enc,
                    raffle_odds,
                    f"Viewers: {info.get('viewers', 'N/A') if info else 'N/A'}",
                    uptime_str,
                    f"Latest Subscriber: {latest_sub}",
                    f"Latest Follower: {latest_follower}",
                    f"Followers: {info.get('followers', 'N/A') if info else 'N/A'}",
                    f"Sub Points: {sub_points if sub_points is not None else 'N/A'}"
                ]
                # Get extra messages (modnews, quotes, derpism, tics, weather)
                extra_messages = await get_ticker_messages()
                # Deduplicate (preserve order, core first)
                seen = set()
                unified = []
                for m in core_messages + extra_messages:
                    if m and m not in seen and m != "N/A" and not m.startswith("[ERROR]"):
                        unified.append(m)
                        seen.add(m)
                if unified:
                    msg = random.choice(unified)
                    await broadcast_overlay_message({"type": "afk_ticker", "message": msg})
                else:
                    await broadcast_overlay_message({"type": "afk_ticker", "message": "AFK: No data available."})
                await asyncio.sleep(0.25)
            except Exception as e:
                logging.error(f"[AFK TICKER ERROR] {e}", exc_info=True)
    async def ticker_cycle_task(self):
        from bot.twitch_stats import get_stream_info, get_sub_points
        from bot.labels_stats import get_ticker_messages, get_raffle_odds_message, get_raffle_encouragement
        while True:
            try:
                info = await get_stream_info()
                sub_points = await get_sub_points()
                raffle_odds = await get_raffle_odds_message()
                raffle_enc = await get_raffle_encouragement()
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
                # Get extra messages (first three are always: encouragement, jackpot, odds, then follower count)
                extra_messages = await get_ticker_messages()
                # Guarantee the first three are always present and never deduplicated out
                # Title always first
                title_msg = f"Title: {info.get('title', 'N/A') if info else 'N/A'}"
                always_present = [title_msg]
                if len(extra_messages) > 0:
                    always_present.append(extra_messages[0])  # encouragement
                if len(extra_messages) > 1:
                    always_present.append(extra_messages[1])  # jackpot
                if len(extra_messages) > 2:
                    always_present.append(extra_messages[2])  # odds
                # Follower count (look for a message starting with 'Followers:')
                follower_msg = next((m for m in extra_messages if m.startswith('Followers:')), None)
                if follower_msg:
                    always_present.append(follower_msg)

                # Core info: always present, never deduplicated out (but skip title)
                core_messages = [
                    f"Latest Subscriber: {latest_sub}",
                    f"Latest Follower: {latest_follower}",
                    f"Viewers: {info.get('viewers', 'N/A') if info else 'N/A'}",
                    uptime_str,
                    f"Sub Points: {sub_points if sub_points is not None else 'N/A'}"
                ]
                # Add label stats (top b/g/d, top 3 g, etc.)
                from bot.labels_stats import read_label
                try:
                    core_messages.extend([
                        f"Top B: {read_label('Top B')}",
                        f"Top G: {read_label('Top G')}",
                        f"Top D: {read_label('Top D')}",
                        f"Top 3 G: {read_label('Top 3 G')}",
                        f"Top 3 D: {read_label('Top 3 D')}",
                        f"Top 3 B: {read_label('Top 3 B')}"
                    ])
                except Exception:
                    pass

                unified = always_present + core_messages
                seen = set(unified)
                # Add the rest of extra_messages, deduplicated
                for m in extra_messages:
                    if m and m not in seen and m != "N/A" and not m.startswith("[ERROR]"):
                        unified.append(m)
                        seen.add(m)
                if unified:
                    full_ticker = ' | '.join(unified)
                    await broadcast_overlay_message({"type": "ticker", "text": full_ticker})
                else:
                    await broadcast_overlay_message({"type": "ticker", "text": "No ticker data available."})
            except Exception as e:
                logging.error(f"[TICKER ERROR] {e}", exc_info=True)
            await asyncio.sleep(0.5)
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
        # AI chat and pirate list logic
        if message.author and message.content:
            import logging
            import os
            from datetime import datetime, timedelta
            content_lower = message.content.lower()
            bot_names = ["@meangenebot", "@mean_gene_bot", "@mean gene bot"]
            if any(name in content_lower for name in bot_names):
                # AI functionality temporarily disabled. Code is preserved for future reactivation.
                return
        # Default: pass to cogs/commands
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
    # Backup raffle state at startup
    backup_raffle_state()

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

    # Register signal handler for graceful shutdown (Ctrl-C)
    def shutdown_handler(signum, frame):
        print("[BOT] Caught shutdown signal, backing up raffle state...")
        backup_raffle_state()
        exit(0)
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

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