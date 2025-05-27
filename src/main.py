print("=== STARTING Mean Gene Bot ===")

import os
import logging
from twitchio.ext import commands
import asyncio
from dotenv import load_dotenv

print("Loaded basic imports.")

try:
    from twitch_commands import load_all_cogs
    print("Imported load_all_cogs from twitch_commands.")
except Exception as e:
    print("FAILED to import load_all_cogs:", e)

os.makedirs("logs", exist_ok=True)
print("Ensured logs directory exists.")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot_debug.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)
print("Logging configured.")

print("Loading .env...")
load_dotenv()
print(".env loaded.")

TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_CHANNELS_RAW = os.getenv("TWITCH_CHANNELS", "yourchannel,iamdar")

print(f"TWITCH_TOKEN: {TWITCH_TOKEN}")
print(f"TWITCH_CLIENT_ID: {TWITCH_CLIENT_ID}")
print(f"TWITCH_CLIENT_SECRET: {TWITCH_CLIENT_SECRET}")
print(f"TWITCH_CHANNELS_RAW: {TWITCH_CHANNELS_RAW}")

if not TWITCH_TOKEN: raise RuntimeError("TWITCH_TOKEN is not set! Check your .env file.")
if not TWITCH_CLIENT_ID: raise RuntimeError("TWITCH_CLIENT_ID is not set! Check your .env file.")
if not TWITCH_CLIENT_SECRET: raise RuntimeError("TWITCH_CLIENT_SECRET is not set! Check your .env file.")
if not TWITCH_CHANNELS_RAW: raise RuntimeError("TWITCH_CHANNELS is not set! Check your .env file.")

TWITCH_CHANNELS = [ch.strip() for ch in TWITCH_CHANNELS_RAW.split(",") if ch.strip()]
print(f"TWITCH_CHANNELS parsed: {TWITCH_CHANNELS}")

def run_twitch_bot(sfx_registry=None):
    print("Entering run_twitch_bot()")
    logger.info("Starting Twitch bot event loop.")
    asyncio.set_event_loop(asyncio.new_event_loop())
    print("Created new asyncio event loop.")
    bot = commands.Bot(
        token=TWITCH_TOKEN,
        prefix="!",
        initial_channels=TWITCH_CHANNELS
    )
    print("Bot instantiated.")
    bot.sfx_registry = sfx_registry  # Make registry available to cogs
    print("About to load all cogs...")
    load_all_cogs(bot)
    print("All cogs loaded. About to run bot...")
    bot.run()
    print("bot.run() returned (should never get here unless bot stops).")

if __name__ == "__main__":
    print("Running as __main__!")
    run_twitch_bot()
    print("End of main.py reached (should never see this unless bot.run() exits).")