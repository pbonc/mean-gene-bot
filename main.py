import os
import sys
import logging
import asyncio
import traceback

from bot import mgb_dwf
from bot.core import MeanGeneBot
from bot.config import TWITCH_TOKEN, BOT_NICK, CHANNEL

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

# --- Async entry point ---
async def main():
    try:
        print("🛠 Constructing MeanGeneBot...")
        bot = MeanGeneBot(sfx_debug=SFX_DEBUG)

        print("🛰️ Starting Discord and Twitch bots concurrently...")
        await asyncio.gather(
            mgb_dwf.start_discord(),
            bot.start()
        )
    except Exception as e:
        print("💥 Bot failed to start.")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
