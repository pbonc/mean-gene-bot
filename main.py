# File: bot/main.py
# Supports CLI flags: -v (verbose), -s (sfx-debug), --dev, --ws
# SFXWatcher tick logging only shown with -v/--verbose

import os
import sys
import logging
import asyncio
import threading
import traceback
import argparse

from flask import Flask, send_from_directory

from bot.core import MeanGeneBot
from bot.config import BOT_NICK, CHANNEL
from bot.loader import load_all
from bot.tasks.sfx_watcher import SFXWatcher  # <-- Import the watcher!
from bot.mgb_dwf import DISCORD_CLIENT, TOKEN as DISCORD_TOKEN  # <-- Import Discord bot!

# --- OAuth bulletproof import ---
from dotenv import load_dotenv
from twitch_token_manager import ensure_valid_token

# --- Bot Version ---
BOT_MAIN_VERSION = "v1.3.4"

# --- Argparse for CLI flags ---
def parse_args():
    parser = argparse.ArgumentParser(description="MeanGeneBot Twitch/Discord Bot")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose debugging output")
    parser.add_argument("-s", "--sfx-debug", action="store_true", help="Enable SFX debug mode")
    parser.add_argument("--dev", action="store_true", help="Developer mode (hot reload, extra checks, etc.)")
    parser.add_argument("--ws", action="store_true", help="Enable WebSocket server (future)")
    return parser.parse_args()

args = parse_args()

# --- Config object ---
class BotConfig:
    def __init__(self, args, twitch_token):
        self.verbose = args.verbose
        self.sfx_debug = args.sfx_debug
        self.dev_mode = args.dev
        self.ws_enabled = args.ws
        self.twitch_token = twitch_token
        self.bot_nick = BOT_NICK
        self.channel = CHANNEL
        self.version = BOT_MAIN_VERSION

# --- Load .env ---
load_dotenv()
TOKEN_PATH = os.getenv("TOKEN_PATH", "tokens.json")
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# --- Bulletproof OAuth token logic ---
try:
    TWITCH_TOKEN = ensure_valid_token(TOKEN_PATH, CLIENT_ID, CLIENT_SECRET)
except Exception as e:
    print(f"Token authentication failed: {e}")
    sys.exit(1)

config = BotConfig(args, TWITCH_TOKEN)

# --- Logging setup ---
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "mean-gene-bot-crash.log"),
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# --- Optional config dump ---
if config.verbose:
    print(f"🎯 TWITCH_TOKEN starts with: {config.twitch_token[:8]}...")
    print(f"🎯 BOT_NICK: {config.bot_nick}")
    print(f"🎯 CHANNEL: {config.channel}")
    print(f"🧪 MAIN VERSION: {config.version}")

# --- Optional TwitchIO check ---
if config.verbose:
    from twitchio.client import Client
    try:
        print("🧪 Testing low-level TwitchIO Client connection...")
        client = Client(token=config.twitch_token)

        @client.event()
        async def event_ready():
            print("✅ LOW-LEVEL event_ready() from Client triggered")

        print("✅ TwitchIO Client initialized (not run — just tested setup)")
    except Exception as e:
        print(f"❌ TwitchIO low-level client failed: {e}")

# --- Async Exception Handler ---
def handle_async_exception(loop, context):
    print("💥 Caught async exception (full context dump):")
    for key, value in context.items():
        print(f"  {key}: {value!r}")
    if "exception" in context and context["exception"]:
        exc = context["exception"]
        print("🔍 Traceback:")
        traceback.print_exception(type(exc), exc, exc.__traceback__)

# --- Fallback global exception hook ---
def global_excepthook(exc_type, exc_value, exc_traceback):
    print("💥 Unhandled exception:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.exit(1)

sys.excepthook = global_excepthook

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_async_exception)

    # Instantiate bot with bulletproof token
    bot = MeanGeneBot(
        sfx_debug=config.sfx_debug,
        verbose=config.verbose,
    )
    # Start SFX Watcher in a thread (if needed)
    sfx_thread = threading.Thread(target=lambda: SFXWatcher(bot, verbose=config.sfx_debug or config.verbose).run(), daemon=True)
    sfx_thread.start()

    # Start the bot
    try:
        loop.run_until_complete(bot.run())
    except Exception as e:
        print(f"❌ Fatal error in bot execution: {e}")
        traceback.print_exc()
        sys.exit(1)