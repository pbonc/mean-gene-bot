import os
import sys
import logging
import asyncio
import traceback

from bot import mgb_dwf
from bot.core import MeanGeneBot
from bot.config import TWITCH_TOKEN, BOT_NICK, CHANNEL

# --- Bot Version ---
BOT_MAIN_VERSION = "v1.3.0"

# Flag control
VERBOSE = "-v" in sys.argv
SFX_DEBUG = "-s" in sys.argv

# Crash log setup
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "mean-gene-bot-crash.log"),
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Optional config diagnostics
if VERBOSE:
    print(f"🎯 TWITCH_TOKEN starts with: {TWITCH_TOKEN[:8]}...")
    print(f"🎯 BOT_NICK: {BOT_NICK}")
    print(f"🎯 CHANNEL: {CHANNEL}")
    print(f"🧪 MAIN VERSION: {BOT_MAIN_VERSION}")

# Optional: low-level TwitchIO client check
if VERBOSE:
    from twitchio.client import Client

    try:
        print("🧪 Testing low-level TwitchIO Client connection...")

        client = Client(token=TWITCH_TOKEN)

        @client.event()
        async def event_ready():
            print("✅ LOW-LEVEL event_ready() from Client triggered")

        print("✅ TwitchIO Client initialized (not run — just tested setup)")
    except Exception as e:
        print(f"❌ TwitchIO low-level client failed: {e}")

# --- Retry Discord Start if Rate-Limited ---
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

# --- Async Entry Point ---
async def main():
    try:
        print("🛠 Constructing MeanGeneBot...")
        bot = MeanGeneBot(sfx_debug=SFX_DEBUG)

        print("🛰️ Starting Discord and Twitch bots concurrently...")
        await asyncio.gather(
            start_discord_with_retry(),
            bot.start()
        )
    except Exception as e:
        print("💥 Bot failed to start.")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
