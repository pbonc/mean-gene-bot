import os
import logging
from twitchio.ext import commands
import aiohttp
import asyncio
from dotenv import load_dotenv

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot_debug.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()  # Load .env from root

# Read credentials and config
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REFRESH_TOKEN = os.getenv("TWITCH_REFRESH_TOKEN")
TWITCH_CHANNELS_RAW = os.getenv("TWITCH_CHANNELS", "yourchannel,iamdar")

# Log presence of secrets/config (don't print actual secrets)
logger.debug(f"TWITCH_TOKEN present: {bool(TWITCH_TOKEN)}")
logger.debug(f"TWITCH_CLIENT_ID present: {bool(TWITCH_CLIENT_ID)}")
logger.debug(f"TWITCH_CLIENT_SECRET present: {bool(TWITCH_CLIENT_SECRET)}")
logger.debug(f"TWITCH_REFRESH_TOKEN present: {bool(TWITCH_REFRESH_TOKEN)}")
logger.debug(f"TWITCH_CHANNELS_RAW: {TWITCH_CHANNELS_RAW}")

if not TWITCH_TOKEN:
    logger.critical("TWITCH_TOKEN is missing from environment! Check your .env file.")
    raise RuntimeError("TWITCH_TOKEN is not set! Check your .env file.")
if not TWITCH_CLIENT_ID:
    logger.critical("TWITCH_CLIENT_ID is missing from environment! Check your .env file.")
    raise RuntimeError("TWITCH_CLIENT_ID is not set! Check your .env file.")
if not TWITCH_CLIENT_SECRET:
    logger.critical("TWITCH_CLIENT_SECRET is missing from environment! Check your .env file.")
    raise RuntimeError("TWITCH_CLIENT_SECRET is not set! Check your .env file.")
if not TWITCH_REFRESH_TOKEN:
    logger.warning("TWITCH_REFRESH_TOKEN is missing from environment (automatic refresh will not work).")
if not TWITCH_CHANNELS_RAW:
    logger.critical("TWITCH_CHANNELS is missing from environment! Check your .env file.")
    raise RuntimeError("TWITCH_CHANNELS is not set! Check your .env file.")

TWITCH_CHANNELS = [ch.strip() for ch in TWITCH_CHANNELS_RAW.split(",") if ch.strip()]

class MeanGeneTwitchBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix="!",
            initial_channels=TWITCH_CHANNELS
        )
        logger.info(f"Initialized MeanGeneTwitchBot for channels: {TWITCH_CHANNELS}")

    async def event_ready(self):
        logger.info(f"Logged in as | {self.nick}")
        for channel in TWITCH_CHANNELS:
            logger.info(f"Joined channel | {channel}")

    async def event_message(self, message):
        await self.handle_commands(message)

    async def event_error(self, error):
        logger.error(f"Twitch error: {error}")
        if "401" in str(error) or "token" in str(error):
            # Likely an OAuth error, try to refresh
            if await self.refresh_token():
                logger.info("Token refreshed, restarting bot...")
                # You may want a more robust restart mechanism; this is a stub
                os.execv(__file__, ['python'] + sys.argv)
            else:
                logger.critical("Could not refresh Twitch token automatically. Exiting.")
                exit(1)

    async def refresh_token(self):
        if not TWITCH_REFRESH_TOKEN:
            logger.error("No refresh token available for Twitch OAuth refresh.")
            return False
        async with aiohttp.ClientSession() as session:
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": TWITCH_REFRESH_TOKEN,
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET
            }
            async with session.post("https://id.twitch.tv/oauth2/token", data=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    new_token = data.get("access_token")
                    if new_token:
                        os.environ["TWITCH_TOKEN"] = new_token
                        logger.info("Twitch OAuth token refreshed successfully.")
                        # NOTE: Consider updating .env or secure storage here as well
                        return True
                    else:
                        logger.error("No new access token in Twitch refresh response.")
                        return False
                else:
                    logger.error(f"Failed to refresh token: {await resp.text()}")
                    return False

def run_twitch_bot():
    logger.info("Starting Twitch bot event loop.")
    asyncio.set_event_loop(asyncio.new_event_loop())
    bot = MeanGeneTwitchBot()
    bot.run()