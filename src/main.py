import os
import logging
from twitchio.ext import commands
import asyncio
from dotenv import load_dotenv

from twitch_commands import load_all_cogs

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot_debug.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_CHANNELS_RAW = os.getenv("TWITCH_CHANNELS", "yourchannel,iamdar")

if not TWITCH_TOKEN: raise RuntimeError("TWITCH_TOKEN is not set! Check your .env file.")
if not TWITCH_CLIENT_ID: raise RuntimeError("TWITCH_CLIENT_ID is not set! Check your .env file.")
if not TWITCH_CLIENT_SECRET: raise RuntimeError("TWITCH_CLIENT_SECRET is not set! Check your .env file.")
if not TWITCH_CHANNELS_RAW: raise RuntimeError("TWITCH_CHANNELS is not set! Check your .env file.")

TWITCH_CHANNELS = [ch.strip() for ch in TWITCH_CHANNELS_RAW.split(",") if ch.strip()]

def run_twitch_bot(sfx_registry):
    logger.info("Starting Twitch bot event loop.")
    asyncio.set_event_loop(asyncio.new_event_loop())
    bot = commands.Bot(
        token=TWITCH_TOKEN,
        prefix="!",
        initial_channels=TWITCH_CHANNELS
    )
    bot.sfx_registry = sfx_registry  # Make registry available to cogs
    load_all_cogs(bot)
    bot.run()