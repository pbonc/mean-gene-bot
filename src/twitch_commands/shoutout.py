import os
import random
import logging
import aiohttp
from twitchio.ext import commands

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DERPISM_FILE = os.path.join(BASE_DIR, "..", "data", "derpisms.txt")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_OAUTH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN")

async def get_last_game(twitch_name):
    """Fetch the last game played by the user using Twitch API."""
    if not TWITCH_CLIENT_ID or not TWITCH_OAUTH_TOKEN:
        return None

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}"
    }

    # Get user ID
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.twitch.tv/helix/users?login={twitch_name}",
            headers=headers
        ) as resp:
            data = await resp.json()
            if "data" not in data or not data["data"]:
                return None
            user_id = data["data"][0]["id"]

        # Get last stream info (if any)
        async with session.get(
            f"https://api.twitch.tv/helix/channels?broadcaster_id={user_id}",
            headers=headers
        ) as resp:
            data = await resp.json()
            if "data" in data and data["data"]:
                return data["data"][0].get("game_name")
    return None

def load_derpisms():
    if not os.path.isfile(DERPISM_FILE):
        return []
    with open(DERPISM_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

class ShoutoutCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger("shoutout")

    @commands.command(name="so")
    async def so(self, ctx: commands.Context):
        parts = ctx.message.content.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].startswith("@"):
            await ctx.send("Usage: !so @username")
            return

        twitchname = parts[1].lstrip("@").strip()
        game = await get_last_game(twitchname)
        if game:
            msg = f"Hey go check out our friend @{twitchname} at https://twitch.tv/{twitchname}! Last seen playing: {game}"
        else:
            msg = f"Hey go check out our friend @{twitchname} at https://twitch.tv/{twitchname}!"
        await ctx.send(msg)

    @commands.command(name="os")
    async def os(self, ctx: commands.Context):
        parts = ctx.message.content.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].startswith("@"):
            await ctx.send("Usage: !os @username")
            return

        twitchname = parts[1].lstrip("@").strip()
        derpisms = load_derpisms()
        if len(derpisms) < 2:
            await ctx.send("Not enough derpisms for anti-shoutout!")
            return
        derp1, derp2 = random.sample(derpisms, 2)
        msg = (
            f"iAmDar is such a {derp1}! Why would you waste your time with such a {derp2}? "
            f"Go check out @{twitchname} at https://twitch.tv/{twitchname}!"
        )
        await ctx.send(msg)

def prepare(bot):
    if not bot.get_cog("ShoutoutCog"):
        bot.add_cog(ShoutoutCog(bot))