# File: bot/main.py
# Refactored for argparse and config structure

import os
import sys
import logging
import asyncio
import threading
import traceback
import argparse

from flask import Flask, send_from_directory

from bot import mgb_dwf
from bot.core import MeanGeneBot
from bot.config import TWITCH_TOKEN, BOT_NICK, CHANNEL
from bot.loader import load_all

# --- Bot Version ---
BOT_MAIN_VERSION = "v1.3.3"

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
    def __init__(self, args):
        self.verbose = args.verbose
        self.sfx_debug = args.sfx_debug
        self.dev_mode = args.dev
        self.ws_enabled = args.ws
        self.twitch_token = TWITCH_TOKEN
        self.bot_nick = BOT_NICK
        self.channel = CHANNEL
        self.version = BOT_MAIN_VERSION

config = BotConfig(args)

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

loop = asyncio.get_event_loop()
loop.set_exception_handler(handle_async_exception)
loop.set_debug(True)

# --- Fallback global exception hook ---
def global_excepthook(exc_type, exc_value, exc_traceback):
    print("💣 GLOBAL EXCEPTION HOOK TRIGGERED")
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    traceback.print_exception(exc_type, exc_value, exc_traceback)

sys.excepthook = global_excepthook

# --- Flask app to serve overlay static files ---
overlay_path = os.path.join(os.path.dirname(__file__), "overlay")
app = Flask(__name__, static_folder=overlay_path)

@app.route('/<path:path>')
def serve_file(path):
    return send_from_directory(app.static_folder, path)

# Debug route to list files in static folder
@app.route('/list-files')
def list_files():
    files = os.listdir(app.static_folder)
    return "<br>".join(files)

def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=config.dev_mode)

# --- Retry Discord Start ---
async def start_discord_with_retry():
    max_retries = 5
    delay = 300  # 5 minutes

    for attempt in range(max_retries):
        try:
            print(f"🔌 Attempting Discord connection (try {attempt + 1}/{max_retries})...")
            await mgb_dwf.start_discord()
            print("✅ Discord bot started successfully.")
            return
        except Exception as e:
            print(f"❌ Discord bot failed to start: {e}")
            if "429" in str(e):
                print(f"⏱️ Rate limited. Retrying in {delay // 60} minutes...")
            else:
                print("💥 Unexpected Discord startup error:")
                traceback.print_exc()
        await asyncio.sleep(delay)

    print("🚫 Max Discord retries exceeded. Skipping Discord startup.")

# --- Async Main Entry ---
async def main():
    try:
        print("🛠 Constructing MeanGeneBot...")
        bot = MeanGeneBot(sfx_debug=config.sfx_debug, dev_mode=config.dev_mode)
        load_all(bot)

        print("🛰️ Starting Flask, Discord and Twitch bots concurrently...")

        # Start Flask server in background thread (non-blocking)
        threading.Thread(target=run_flask, daemon=True).start()

        # Run Discord startup retry and Twitch bot concurrently
        await asyncio.gather(
            start_discord_with_retry(),
            bot.start()
        )
    except Exception as e:
        print("💥 Bot failed to start.")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())