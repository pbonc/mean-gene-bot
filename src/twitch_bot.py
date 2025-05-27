import os
import logging
from twitchio.ext import commands
import aiohttp

# Load environment variables for credentials and channels
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REFRESH_TOKEN = os.getenv("TWITCH_REFRESH_TOKEN")
TWITCH_CHANNELS = os.getenv("TWITCH_CHANNELS", "yourchannel,iamdar").split(",")

class MeanGeneTwitchBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix="!",
            initial_channels=[ch.strip() for ch in TWITCH_CHANNELS]
        )

    async def event_ready(self):
        logging.info(f"Logged in as | {self.nick}")
        for channel in TWITCH_CHANNELS:
            logging.info(f"Joined channel | {channel}")

    async def event_message(self, message):
        await self.handle_commands(message)

    async def event_error(self, error):
        logging.error(f"Twitch error: {error}")
        if "401" in str(error) or "token" in str(error):
            # Likely an OAuth error, try to refresh
            if await self.refresh_token():
                logging.info("Token refreshed, restarting bot...")
                os.execv(__file__, ['python'] + sys.argv)
            else:
                logging.critical("Could not refresh Twitch token automatically. Exiting.")
                exit(1)

    async def refresh_token(self):
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
                    os.environ["TWITCH_TOKEN"] = data["access_token"]
                    # Optionally update .env or secrets storage
                    return True
                else:
                    logging.error(f"Failed to refresh token: {await resp.text()}")
                    return False

def run_twitch_bot():
    logging.basicConfig(level=logging.INFO)
    bot = MeanGeneTwitchBot()
    bot.run()