import shutil
import signal
from bot.audio_manager import AudioManager

_SINGLE_INSTANCE_MUTEX = None


def _acquire_single_instance_lock() -> bool:
    """Prevent multiple bot.main processes from running simultaneously on Windows."""
    global _SINGLE_INSTANCE_MUTEX
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mutex_name = "Local\\MeanGeneBotMainSingleton"
        _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, mutex_name)
        ERROR_ALREADY_EXISTS = 183
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        # If lock creation fails, do not block startup.
        return True


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
import time
from twitchio.ext import commands
from dotenv import load_dotenv
try:
    import discord
    from discord.ext import commands as discord_commands
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    print("[DISCORD] discord.py not available, Discord features disabled")
from bot.overlay_server import start_overlay_server, broadcast_overlay_message
from bot.weather_utils import fetch_weather, save_weather_message, get_random_weather_messages, get_any_weather_message
from bot.oauth_refresh import auto_refresh_if_needed
from bot.telemetry import log_event, tail_events, telemetry_file_path
from bot.twitch_watchdog import TwitchWatchdogState, WatchdogAction

# Auto-install dependencies on startup
try:
    from bot.dependency_manager import DependencyManager
    
    # Check if we should auto-install dependencies
    AUTO_INSTALL = os.getenv("AUTO_INSTALL_DEPENDENCIES", "false").lower() == "true"
    
    if AUTO_INSTALL:
        print("🔧 Auto-installing dependencies (AUTO_INSTALL_DEPENDENCIES=true)...")
        manager = DependencyManager()
        manager.install_missing_dependencies()
        print("✅ Dependency check complete!")
    else:
        # Just check and report status
        print("🔍 Checking dependency status...")
        manager = DependencyManager()
        status = manager.get_dependency_status()
        
        missing_core = [pkg for pkg, status in status["core"].items() if "Missing" in status]
        missing_optional = [pkg for pkg, info in status["optional"].items() 
                          if isinstance(info, dict) and "Missing" in info["status"]]
        available_optional = [pkg for pkg, info in status["optional"].items() 
                            if isinstance(info, dict) and "Available" in info["status"]]
        
        if missing_core:
            print(f"⚠️ Missing core dependencies: {', '.join(missing_core)}")
            print("💡 Set AUTO_INSTALL_DEPENDENCIES=true in .env or run: python -m bot.dependency_manager")
        
        if available_optional:
            print(f"🎵 Music features available: {', '.join(available_optional)}")
        
        if missing_optional:
            if available_optional:  # Some available, some missing
                print(f"ℹ️ Additional music features available with: {', '.join(missing_optional)}")
            else:  # None available
                print(f"ℹ️ Optional music features unavailable: {', '.join(missing_optional)}")
            print(f"📦 Install with: pip install {' '.join(missing_optional)}")

except ImportError:
    print("⚠️ Dependency manager not available. Install requirements manually if needed.")
except Exception as e:
    print(f"⚠️ Dependency check error: {e}")


# Load .env file
load_dotenv()

# Instantiate global AudioManager
audio_manager = AudioManager(music_volume=0.3, sfx_volume=0.6, duck_volume=0.1)

# Import Discord config after loading .env
try:
    from bot.config import DISCORD_TOKEN, DISCORD_CHANNEL_ID
except ImportError as e:
    print(f"[CONFIG] Error importing Discord config: {e}")
    DISCORD_TOKEN = None
    DISCORD_CHANNEL_ID = None

TWITCH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_BOT_ID = os.getenv("TWITCH_BOT_ID")
TWITCH_CHANNELS = os.getenv("TWITCH_CHANNELS", "").split(",")


def _normalize_twitch_token(token: str | None) -> str | None:
    if not token:
        return token
    return token.replace("oauth:", "")


TWITCH_TOKEN = _normalize_twitch_token(TWITCH_TOKEN)

YOUTUBE_PROMO_URL = "https://www.youtube.com/@iamdartv"
YOUTUBE_PROMO_INTERVAL_SECONDS = 15 * 60
YOUTUBE_PROMO_MESSAGE = f"Check out my YouTube channel: {YOUTUBE_PROMO_URL}"

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def _prune_old_log_files(log_dir: str, keep_count: int = 10):
    """Keep only the newest log files to prevent unbounded growth."""
    try:
        log_files = [
            os.path.join(log_dir, name)
            for name in os.listdir(log_dir)
            if name.lower().endswith(".log") and os.path.isfile(os.path.join(log_dir, name))
        ]
        log_files.sort(key=os.path.getmtime, reverse=True)
        for old_log in log_files[keep_count:]:
            os.remove(old_log)
    except Exception as e:
        # Logging may not be initialized yet; avoid crashing startup over cleanup.
        print(f"[LOG CLEANUP] Failed to prune log files: {e}")


LOG_FILE = os.path.join(LOG_DIR, f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
DISABLED_COMMANDS = set()
logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO,
    force=True,
)
_prune_old_log_files(LOG_DIR, keep_count=10)

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
        from bot.twitch_stats import get_stream_info
        from bot.labels_stats import get_ticker_messages, get_raffle_odds_message, get_raffle_encouragement, read_follower_count
        refresh_interval = 30
        last_refresh = 0.0
        cached_info = None
        cached_raffle_odds = None
        cached_raffle_enc = None
        while True:
            try:
                now = time.monotonic()
                if (now - last_refresh) >= refresh_interval:
                    cached_info = await get_stream_info()
                    cached_raffle_odds = await get_raffle_odds_message()
                    cached_raffle_enc = await get_raffle_encouragement()
                    last_refresh = now

                info = cached_info
                raffle_odds = cached_raffle_odds
                raffle_enc = cached_raffle_enc
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
                follower_count = "N/A"
                sub_points = "N/A"
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
                try:
                    follower_count = read_follower_count()
                except Exception:
                    pass
                try:
                    sub_points_path = os.path.join(labels_dir, "total_subscriber_score.txt")
                    if os.path.isfile(sub_points_path):
                        with open(sub_points_path, "r", encoding="utf-8") as f:
                            sub_points = f.read().strip() or "N/A"
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
                    f"Followers: {follower_count}",
                    f"Sub Points: {sub_points}"
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
                # AFK ticker: send messages very frequently so the AFK overlay will
                # display many concurrent rows. Reducing to 1s produces a denser
                # matrix (typically ~40-60 visible rows given 40-60s animations).
                # Monitor performance; if this proves noisy we can dial back to 2-3s
                # or implement a burst-on-start plus a steadier cadence.
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                logging.info("[AFK TICKER] Cancelled via shutdown request")
                raise
            except Exception as e:
                logging.error(f"[AFK TICKER ERROR] {e}", exc_info=True)

    async def ticker_cycle_task(self):
        from bot.twitch_stats import get_stream_info
        from bot.labels_stats import get_ticker_messages, get_raffle_odds_message, get_raffle_encouragement, read_follower_count
        while True:
            try:
                info = await get_stream_info()
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
                follower_count = "N/A"
                sub_points = "N/A"
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
                try:
                    follower_count = read_follower_count()
                except Exception:
                    pass
                try:
                    sub_points_path = os.path.join(labels_dir, "total_subscriber_score.txt")
                    if os.path.isfile(sub_points_path):
                        with open(sub_points_path, "r", encoding="utf-8") as f:
                            sub_points = f.read().strip() or "N/A"
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
                else:
                    always_present.append(f"Followers: {follower_count}")

                # Core info: always present, never deduplicated out (but skip title)
                core_messages = [
                    f"Latest Subscriber: {latest_sub}",
                    f"Latest Follower: {latest_follower}",
                    f"Followers: {follower_count}",
                    f"Viewers: {info.get('viewers', 'N/A') if info else 'N/A'}",
                    uptime_str,
                    f"Sub Points: {sub_points}"
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
                try:
                    from bot.fishing.service import get_fishing_service
                    core_messages.extend(await get_fishing_service().ticker_messages())
                except Exception as fishing_ticker_error:
                    logging.warning(f"[FISHING] Could not add fishing ticker stats: {fishing_ticker_error}")

                unified = always_present + core_messages
                seen = set(unified)
                # Add the rest of extra_messages, deduplicated
                for m in extra_messages:
                    if m and m not in seen and m != "N/A" and not m.startswith("[ERROR]"):
                        unified.append(m)
                        seen.add(m)
                if unified:
                    # Prepend a timestamp (CST and UTC) so the ticker always
                    # starts with the current times before the Title.
                    # Build a robust timestamp that prefers zoneinfo but falls
                    # back to other methods if unavailable (common on Windows
                    # without tzdata installed). The goal is to avoid "N/A".
                    try:
                        from datetime import datetime, timezone, timedelta
                        timestamp_msg = None
                        try:
                            # Prefer stdlib zoneinfo (Python 3.9+)
                            from zoneinfo import ZoneInfo
                            now_utc = datetime.now(timezone.utc)
                            cst = now_utc.astimezone(ZoneInfo("America/Chicago")).strftime("%I:%M %p").lstrip('0')
                            gmt = now_utc.astimezone(ZoneInfo("UTC")).strftime("%H:%M")
                            timestamp_msg = f"{cst} CST | {gmt} GMT"
                        except Exception:
                            # Try pytz if available
                            try:
                                import pytz
                                now_utc = datetime.now(pytz.utc)
                                cst = now_utc.astimezone(pytz.timezone("America/Chicago")).strftime("%I:%M %p").lstrip('0')
                                gmt = now_utc.astimezone(pytz.utc).strftime("%H:%M")
                                timestamp_msg = f"{cst} CST | {gmt} GMT"
                            except Exception:
                                # Last-resort fallback: use UTC and approximate CST as UTC-6
                                now = datetime.utcnow()
                                gmt = now.strftime("%H:%M")
                                approx_cst = (now - timedelta(hours=6)).strftime("%I:%M %p").lstrip('0')
                                timestamp_msg = f"{approx_cst} CST | {gmt} GMT"
                        if not timestamp_msg:
                            timestamp_msg = "N/A CST | N/A GMT"
                    except Exception:
                        timestamp_msg = "N/A CST | N/A GMT"

                    full_ticker = ' | '.join([timestamp_msg] + unified)
                    await broadcast_overlay_message({"type": "ticker", "text": full_ticker})
                else:
                    await broadcast_overlay_message({"type": "ticker", "text": "No ticker data available."})
            except asyncio.CancelledError:
                logging.info("[TICKER] Cancelled via shutdown request")
                raise
            except Exception as e:
                logging.error(f"[TICKER ERROR] {e}", exc_info=True)
            # Wait ~60 seconds between full-ticker broadcasts to overlays
            # This makes a new ticker string at roughly one-minute intervals.
            await asyncio.sleep(60)
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
            client_secret=TWITCH_CLIENT_SECRET,
            bot_id=TWITCH_BOT_ID,
            prefix='!',
            initial_channels=TWITCH_CHANNELS
        )
        self.discord_client = None
        self._last_twitch_activity = time.monotonic()

    def _touch_twitch_activity(self):
        self._last_twitch_activity = time.monotonic()

    async def event_ready(self):
        self._touch_twitch_activity()
        print(f"Logged in as | {self.nick}")
        # Don't broadcast an initial ticker on startup — overlays should
        # receive only canonical ticker strings produced by the ticker task.
        # Keep a simple console log for visibility.
        logging.info("Bot ready — ticker task will produce overlay messages shortly.")

    async def event_message(self, message):
        self._touch_twitch_activity()
        author_name = message.author.name if message.author else "Unknown"
        print(f"Message from {author_name}: {message.content}")
        if message.author and not getattr(message, "echo", False):
            try:
                await broadcast_overlay_message(
                    {"type": "wotwom_chat_user", "username": author_name}
                )
            except Exception:
                logging.debug(
                    "[WOTWOM] Failed to broadcast active chatter",
                    exc_info=True,
                )
        try:
            content = message.content or ""
            is_command = bool(content.startswith("!"))
            log_event(
                "chat_message",
                {
                    "author": author_name,
                    "channel": getattr(getattr(message, "channel", None), "name", None),
                    "content": content,
                    "is_command": is_command,
                    "is_echo": bool(getattr(message, "echo", False)),
                },
            )
            if is_command:
                parts = content.split()
                command_name = parts[0][1:].lower() if parts else ""
                command_args = parts[1:] if len(parts) > 1 else []
                if command_name in DISABLED_COMMANDS:
                    logging.info("[COMMAND] Blocked disabled command '%s' from %s", command_name, author_name)
                    return
                log_event(
                    "command_issued",
                    {
                        "author": author_name,
                        "channel": getattr(getattr(message, "channel", None), "name", None),
                        "command": command_name,
                        "args": command_args,
                        "raw": content,
                    },
                )
        except Exception as exc:
            logging.error(f"[TELEMETRY] Failed to log event_message: {exc}")
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
        # Default: pass to base event so listeners/cogs fire
        await super().event_message(message)

    async def event_command(self, ctx):
        self._touch_twitch_activity()
        try:
            if ctx and ctx.command:
                log_event(
                    "command_executed",
                    {
                        "author": getattr(getattr(ctx, "author", None), "name", None),
                        "channel": getattr(getattr(ctx, "channel", None), "name", None),
                        "command": getattr(ctx.command, "name", None),
                        "message": getattr(getattr(ctx, "message", None), "content", None),
                    },
                )
        except Exception as exc:
            logging.error(f"[TELEMETRY] Failed to log event_command: {exc}")

    async def event_command_error(self, ctx, error):
        self._touch_twitch_activity()
        try:
            log_event(
                "command_error",
                {
                    "author": getattr(getattr(ctx, "author", None), "name", None),
                    "channel": getattr(getattr(ctx, "channel", None), "name", None),
                    "command": getattr(getattr(ctx, "command", None), "name", None),
                    "message": getattr(getattr(ctx, "message", None), "content", None),
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
        except Exception as exc:
            logging.error(f"[TELEMETRY] Failed to log event_command_error: {exc}")

    async def _send_youtube_promo(self, source: str = "manual", skip_channel_name: str | None = None):
        sent_count = 0
        channels = list(getattr(self, "connected_channels", None) or [])
        for channel in channels:
            channel_name = getattr(channel, "name", None)
            if skip_channel_name and channel_name == skip_channel_name:
                continue
            try:
                await channel.send(YOUTUBE_PROMO_MESSAGE)
                sent_count += 1
            except Exception as exc:
                logging.warning("[YT PROMO] Failed to send in channel %s: %s", channel_name or "unknown", exc)

        if sent_count == 0:
            logging.info("[YT PROMO] Skipped (%s): no connected channels", source)
        else:
            logging.info("[YT PROMO] Sent (%s) to %s channel(s)", source, sent_count)

        return sent_count

    async def youtube_promo_cycle_task(self):
        while True:
            try:
                await asyncio.sleep(YOUTUBE_PROMO_INTERVAL_SECONDS)
                await self._send_youtube_promo(source="timer")
            except asyncio.CancelledError:
                logging.info("[YT PROMO] Cancelled via shutdown request")
                raise
            except Exception as exc:
                logging.error("[YT PROMO] Unexpected error: %s", exc, exc_info=True)

    @commands.command(name='hello')
    async def hello(self, ctx):
        await ctx.send(f"Hello, {ctx.author.name}!")

    @commands.command(name="yt")
    async def yt_command(self, ctx):
        await ctx.send(YOUTUBE_PROMO_MESSAGE)
        sent_elsewhere = await self._send_youtube_promo(
            source=f"command:{getattr(ctx.author, 'name', 'unknown')}",
            skip_channel_name=getattr(getattr(ctx, "channel", None), "name", None),
        )
        if sent_elsewhere > 0:
            logging.info("[YT PROMO] !yt triggered by %s; command message sent plus %s channel broadcast(s)", getattr(ctx.author, "name", "unknown"), sent_elsewhere)

    @commands.command(name='reviewlog', aliases=('latestlog',))
    async def reviewlog(self, ctx, count: str = "20", event_type: str = None):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use this command.")
            return

        try:
            limit = max(1, min(50, int(count)))
        except Exception:
            await ctx.send("Usage: !reviewlog [count 1-50] [event_type]")
            return

        events = tail_events(limit=limit, event_type=event_type)
        if not events:
            await ctx.send(
                f"No telemetry events found. File: {os.path.basename(telemetry_file_path())}"
            )
            return

        preview = events[-8:]
        lines = []
        for item in preview:
            ts = item.get("ts", "?")
            et = item.get("event_type", "?")
            author = item.get("author")
            command = item.get("command")
            phase = item.get("phase")
            if command:
                lines.append(f"{ts} {et} @{author} !{command}")
            elif phase:
                lines.append(f"{ts} {et} phase={phase}")
            else:
                lines.append(f"{ts} {et}")

        message = " | ".join(lines)
        if len(message) > 460:
            message = message[:457] + "..."

        await ctx.send(message)

    # Example overlay command for you to adjust
    @commands.command(name='overlaytest')
    async def overlaytest(self, ctx):
        # This will display the test image on the overlay
        await broadcast_overlay_message({"image": "/gifs/darheart2.jpg"})
        await ctx.send("Overlay image triggered!")

    @commands.command(name='reloadrpg')
    async def reloadrpg(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use this command.")
            return
        await ctx.send("RPG functionality has been archived; reload is no longer supported in this repository.")

if DISCORD_AVAILABLE:
    class DiscordBot(discord_commands.Bot):
        def __init__(self):
            intents = discord.Intents.default()
            intents.message_content = True
            super().__init__(command_prefix='!', intents=intents)
            
        async def on_ready(self):
            print(f'[DISCORD] Bot logged in as {self.user}')
            
        async def send_to_channel(self, message):
            if DISCORD_CHANNEL_ID:
                channel = self.get_channel(DISCORD_CHANNEL_ID)
                if channel:
                    await channel.send(message)
                else:
                    print(f'[DISCORD ERROR] Channel {DISCORD_CHANNEL_ID} not found')
            else:
                print('[DISCORD ERROR] No channel ID configured')
else:
    # Dummy DiscordBot class when Discord is not available
    class DiscordBot:
        def __init__(self):
            pass
        async def start(self, token):
            pass
        async def send_to_channel(self, message):
            print(f'[DISCORD DISABLED] Would send: {message}')

async def main():
    if not _acquire_single_instance_lock():
        print("[BOT] Another bot.main instance is already running. Exiting this duplicate process.")
        return

    # Backup raffle state at startup
    backup_raffle_state()

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\n[BOT] Received signal {signum}, shutting down gracefully...")
        # Kill any music processes using brute force approach
        try:
            import subprocess
            # Kill any python processes that might be playing audio
            try:
                subprocess.run(['taskkill', '/F', '/IM', 'python.exe'], 
                             capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                print("[BOT] Killed any remaining python audio processes")
            except Exception as e:
                print(f"[BOT] Error killing processes: {e}")
        except Exception as e:
            print(f"[BOT] Error cleaning up audio: {e}")
        
        # Exit the program
        import sys
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
    
    print("[BOT] Signal handlers registered for graceful shutdown.")

    # Check and refresh Twitch token if needed
    print("[BOT] Validating Twitch authentication...")
    try:
        success, auth_msg = auto_refresh_if_needed()
        if success:
            print(f"[BOT] Authentication OK: {auth_msg}")
            # Re-read environment after possible refresh and normalize token format.
            load_dotenv(override=True)
            global TWITCH_TOKEN
            TWITCH_TOKEN = _normalize_twitch_token(os.getenv("TWITCH_OAUTH_TOKEN"))

            # Optional diagnostics: warn when token user does not match configured bot identity.
            try:
                from bot.oauth_refresh import get_twitch_token_details

                token_ok, token_details = get_twitch_token_details(TWITCH_TOKEN)
                if token_ok:
                    token_login = (token_details.get("login") or "").strip().lower()
                    configured_bot = (TWITCH_BOT_ID or "").strip().lower()
                    if configured_bot and token_login and configured_bot != token_login:
                        print(
                            "[BOT] WARNING: TWITCH_BOT_ID does not match token owner "
                            f"(configured='{configured_bot}', token='{token_login}')."
                        )
                        print("[BOT] Commands may fail if bot identity and token owner differ.")
                else:
                    print(f"[BOT] Token detail check warning: {token_details}")
            except Exception as token_diag_error:
                print(f"[BOT] Token diagnostics unavailable: {token_diag_error}")
        else:
            print(f"[BOT] Authentication issue: {auth_msg}")
            print("[BOT] Continuing startup, but Twitch connection may fail...")
    except Exception as auth_error:
        print(f"[BOT] Error checking authentication: {auth_error}")
        print("[BOT] Continuing startup, but Twitch connection may fail...")

    async def start_overlay_server_resilient():
        host = (os.getenv("OVERLAY_HOST") or "0.0.0.0").strip() or "0.0.0.0"
        configured_port = (os.getenv("OVERLAY_PORT") or "8080").strip()
        try:
            base_port = int(configured_port)
        except ValueError:
            print(f"[OVERLAY] Invalid OVERLAY_PORT '{configured_port}', defaulting to 8080")
            base_port = 8080

        for port in (base_port, base_port + 1, base_port + 2):
            try:
                await start_overlay_server(host=host, port=port)
                return
            except OSError as overlay_error:
                # WinError 10048: address already in use.
                if getattr(overlay_error, "errno", None) == 10048:
                    print(f"[OVERLAY] Port {port} is already in use, trying next port...")
                    continue
                raise

        print(
            f"[OVERLAY] Disabled: no available ports in range {base_port}-{base_port + 2}. "
            "Twitch/Discord bot will continue without overlay server."
        )

    # Start the overlay server in the background
    overlay_task = asyncio.create_task(start_overlay_server_resilient())
    discord_bot = None
    bot = None
    ticker_task = None
    afk_ticker_task = None
    youtube_promo_task = None
    connection_watchdog_task = None

    async def _force_close_twitch(bot_instance):
        connection = getattr(bot_instance, "_connection", None)
        if connection:
            keeper = getattr(connection, "_keeper", None)
            if keeper and not getattr(keeper, "cancelled", lambda: False)():
                keeper.cancel()
            cleaner = getattr(connection, "_task_cleaner", None)
            if cleaner and not cleaner.done():
                cleaner.cancel()
            for task in getattr(connection, "_background_tasks", []):
                if task and not task.done():
                    task.cancel()
            websocket = getattr(connection, "_websocket", None)
            if websocket and not websocket.closed:
                await websocket.close()
        http = getattr(bot_instance, "_http", None)
        session = getattr(http, "session", None)
        if session and not session.closed:
            await session.close()

    async def shutdown_cleanup():
        print("[BOT] Cleaning up bot connections...")
        if discord_bot:
            try:
                await discord_bot.close()
            except Exception as close_error:
                print(f"[DISCORD] Error during close: {close_error}")      
        try:
            if bot:
                await bot.close()
        except AttributeError as close_error:
            print(f"[BOT] Twitch client already cleaned up: {close_error}")
        except Exception as close_error:
            print(f"[BOT] Error while closing Twitch bot: {close_error}")  
        finally:
            if bot:
                await _force_close_twitch(bot)
        for extra_task in (overlay_task, ticker_task, afk_ticker_task, youtube_promo_task, connection_watchdog_task):
            if extra_task and not extra_task.done():
                extra_task.cancel()
        for extra_task in (overlay_task, ticker_task, afk_ticker_task, youtube_promo_task, connection_watchdog_task):
            if not extra_task:
                continue
            try:
                await extra_task
            except asyncio.CancelledError:
                pass

    # Create and start the bots
    try:
        print("[BOT] Initializing TwitchIO Bot...")
        bot = Bot()
        print("[BOT] TwitchIO Bot initialized successfully")
    except Exception as bot_init_error:
        print(f"[BOT] CRITICAL: Failed to initialize TwitchIO Bot: {type(bot_init_error).__name__}: {bot_init_error}")
        import traceback
        traceback.print_exc()
        print("[BOT] Bot initialization failed. Exiting.")
        await shutdown_cleanup()
        raise
    
    # Initialize Discord bot if token is provided
    discord_bot = None
    if DISCORD_AVAILABLE and DISCORD_TOKEN:
        try:
            discord_bot = DiscordBot()
            bot.discord_client = discord_bot
            print('[DISCORD] Discord integration enabled')
        except Exception as discord_error:
            print(f'[DISCORD] Error setting up Discord: {discord_error}')
            print('[DISCORD] Continuing without Discord integration')
            discord_bot = None
    else:
        if not DISCORD_AVAILABLE:
            print('[DISCORD] discord.py not available, Discord integration disabled')
        else:
            print('[DISCORD] Discord token not found, Discord integration disabled')

    # Start ticker cycle tasks
    ticker_task = asyncio.create_task(bot.ticker_cycle_task())
    afk_ticker_task = asyncio.create_task(bot.afk_ticker_cycle_task())
    youtube_promo_task = asyncio.create_task(bot.youtube_promo_cycle_task())

    # Automatically load all cogs in bot/commands/
    commands_dir = os.path.join(os.path.dirname(__file__), "commands")
    manual_exclusions = {"__init__.py", "base_command.py", "analytics_cog.py"}
    archived_prefixes = ("rpg_cog",)
    if os.path.isdir(commands_dir):
        for filename in os.listdir(commands_dir):
            if not filename.endswith(".py"):
                continue
            if filename in manual_exclusions:
                continue
            if any(filename.startswith(prefix) for prefix in archived_prefixes):
                print(f"[COG] Skipping archived cog {filename}")
                continue
            modulename = f"bot.commands.{filename[:-3]}"
            try:
                print(f"[COG] Loading {modulename}...")
                module = importlib.import_module(modulename)
                if hasattr(module, "prepare"):
                    module.prepare(bot)
                    print(f"[COG] ✅ {filename} loaded successfully")
                else:
                    print(f"[COG] ⚠️ {filename} has no prepare function")
            except Exception as e:
                print(f"[COG] ❌ Failed to load {filename}: {e}")
                import traceback
                traceback.print_exc()
    # Load modnews cog
    from bot.commands.modnews import prepare as modnews_prepare
    modnews_prepare(bot)

    main_task_ref = {"task": None, "shutting_down": False}

    def cancel_main_task():
        task = main_task_ref.get("task")
        if task and not task.done():
            task.cancel()

    def shutdown_handler(signum, frame):
        if main_task_ref.get("shutting_down"):
            return
        main_task_ref["shutting_down"] = True
        print("[BOT] Caught shutdown signal, backing up raffle state...")
        try:
            backup_raffle_state()
        except Exception as err:
            print(f"[BOT] Failed to back up raffle state: {err}")
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(cancel_main_task)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Helper that suppresses the TwitchIO keeper race on shutdown
    async def run_bot_start(coro_factory, label):
        try:
            await coro_factory()
            if not main_task_ref.get("shutting_down"):
                raise RuntimeError(f"{label} stopped unexpectedly")
        except AttributeError as err:
            err_msg = err.args[0] if err.args else ""
            if "NoneType' object has no attribute 'cancel'" in err_msg:
                print(f"[BOT] {label} shutdown race suppressed: {err_msg}")
                return
            raise

    async def twitch_connection_watchdog():
        """Detect sustained Twitch disconnects without fighting TwitchIO reconnects."""
        reconnect_grace_seconds = max(
            60,
            int(os.getenv("TWITCH_RECONNECT_GRACE_SECONDS", "300")),
        )
        watchdog_state = TwitchWatchdogState(reconnect_grace_seconds)
        while True:
            await asyncio.sleep(30)
            if main_task_ref.get("shutting_down") or not bot:
                continue
            try:
                idle_for = time.monotonic() - getattr(bot, "_last_twitch_activity", time.monotonic())
                channels = getattr(bot, "connected_channels", None) or []
                connection = getattr(bot, "_connection", None)
                websocket = getattr(connection, "_websocket", None) if connection else None
                websocket_closed = bool(websocket and getattr(websocket, "closed", False))

                unhealthy_reason = None
                if websocket_closed:
                    unhealthy_reason = "Twitch websocket is closed"
                elif idle_for > 180 and not channels:
                    unhealthy_reason = f"No connected Twitch channels for {int(idle_for)}s"

                result = watchdog_state.observe(bool(unhealthy_reason), time.monotonic())
                if result.action == WatchdogAction.DISCONNECT_STARTED:
                    logging.warning(
                        "[WATCHDOG] %s; allowing TwitchIO up to %ss to reconnect",
                        unhealthy_reason,
                        reconnect_grace_seconds,
                    )
                elif result.action == WatchdogAction.RECOVERED:
                    logging.info(
                        "[WATCHDOG] Twitch connection recovered after %ss",
                        int(result.disconnected_for),
                    )
                elif result.action == WatchdogAction.GRACE_EXCEEDED:
                    raise RuntimeError(
                        f"{unhealthy_reason}; reconnect grace exceeded "
                        f"({int(result.disconnected_for)}s)"
                    )
            except Exception as watchdog_error:
                logging.error("[WATCHDOG] Twitch health check failed: %s", watchdog_error, exc_info=True)
                raise

    def reload_twitch_token_for_retry():
        global TWITCH_TOKEN
        load_dotenv(override=True)
        latest_token = os.getenv("TWITCH_OAUTH_TOKEN")
        if not latest_token:
            return False, "TWITCH_OAUTH_TOKEN is missing after refresh"

        # Keep a normalized token shape for TwitchIO internals.
        normalized_token = latest_token.replace("oauth:", "")
        TWITCH_TOKEN = normalized_token

        if bot:
            http_client = getattr(bot, "_http", None)
            if http_client is not None:
                http_client.token = normalized_token

            connection = getattr(bot, "_connection", None)
            if connection is not None:
                connection._token = normalized_token

        return True, "Runtime token reloaded"

    # Start both bots concurrently
    print("[BOT] Starting Twitch bot...")
    tasks = [run_bot_start(bot.start, "Twitch bot")]
    
    if discord_bot:
        print("[BOT] Adding Discord bot to tasks...")
        tasks.append(run_bot_start(lambda: discord_bot.start(DISCORD_TOKEN), "Discord bot"))
    
    connection_watchdog_task = asyncio.create_task(twitch_connection_watchdog())

    print(f"[BOT] Running {len(tasks)} bot tasks + overlay + ticker...")
    async def create_main_gather(task_group):
        gather_task = asyncio.gather(
            *task_group,
            overlay_task,
            ticker_task,
            afk_ticker_task,
            youtube_promo_task,
            connection_watchdog_task,
        )
        main_task_ref["task"] = gather_task
        return gather_task

    # Run all tasks concurrently, with a single automatic retry on auth errors
    try:
        print("[BOT] Starting overlay server...")
        print("[BOT] Starting ticker tasks...")
        main_gather = await create_main_gather(tasks)
        await main_gather
    except asyncio.CancelledError:
        print("[BOT] Main gather cancelled due to shutdown signal.")
    except Exception as e:
        error_msg = str(e)
        print(f"[BOT] Error in main gather: {error_msg}")
        logging.error(f"[BOT] Main gather error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()

        # Check if it's an authentication error and try to refresh token
        if "Invalid or unauthorized Access Token" in error_msg or "401" in error_msg:
            print("[BOT] Detected authentication error, attempting token refresh...")
            try:
                success, refresh_msg = auto_refresh_if_needed()
                if success:
                    print(f"[BOT] Token refresh successful: {refresh_msg}")
                    token_reload_ok, token_reload_msg = reload_twitch_token_for_retry()
                    if token_reload_ok:
                        print(f"[BOT] {token_reload_msg}")
                    else:
                        print(f"[BOT] Token reload warning: {token_reload_msg}")
                    # Attempt an automatic restart of bot tasks once
                    print("[BOT] Attempting automatic restart of bot tasks...")
                    try:
                        # Recreate tasks to avoid reusing failed coroutines
                        new_tasks = [run_bot_start(bot.start, "Twitch bot retry")]
                        if discord_bot:
                            new_tasks.append(run_bot_start(lambda: discord_bot.start(DISCORD_TOKEN), "Discord bot retry"))
                        retry_gather = await create_main_gather(new_tasks)
                        await retry_gather
                        return
                    except Exception as retry_error:
                        print(f"[BOT] Retry failed: {retry_error}")
                        logging.error(f"[BOT] Retry gather error: {retry_error}", exc_info=True)
                        print("[BOT] Please restart the bot to use the refreshed token.")
                        raise
                else:
                    print(f"[BOT] Token refresh failed: {refresh_msg}")
                    print("[BOT] Please manually refresh your Twitch OAuth token.")
                    raise RuntimeError(refresh_msg)
            except Exception as refresh_error:
                print(f"[BOT] Error during token refresh: {refresh_error}")
                raise

        if not main_task_ref.get("shutting_down"):
            raise
    finally:
        await shutdown_cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"[BOT FATAL ERROR] {e}", exc_info=True)
