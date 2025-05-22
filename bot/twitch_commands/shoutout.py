import re
from twitchio.ext import commands

SHOUTOUT_TEMPLATE = (
    "📣 Check out @{target} at https://twitch.tv/{target} — they're a great streamer worth your time!"
)
ANTISHOUT_TEMPLATE = (
    "💩 @iamdar is a dumpster fire and you deserve better. "
    "Go watch @{target} at https://twitch.tv/{target} instead. Please. Save yourself."
)

# Valid Twitch username: 4-25 characters, alphanumeric or underscore
TWITCH_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{4,25}$")

class Shoutout(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("📢 Shoutout Cog initialized")

    @commands.command(name="shoutout", aliases=["so"])
    async def shoutout(self, ctx: commands.Context):
        parts = ctx.message.content.strip().split()
        if len(parts) < 2:
            await ctx.send("⚠️ Usage: !shoutout <username>")
            return

        target = parts[1].lstrip("@").strip()
        if not TWITCH_USERNAME_RE.fullmatch(target):
            await ctx.send("⚠️ Invalid username.")
            return

        message = SHOUTOUT_TEMPLATE.format(target=target.lower())
        await ctx.send(message)

    @commands.command(name="os")
    async def anti_shoutout(self, ctx: commands.Context):
        parts = ctx.message.content.strip().split()
        if len(parts) < 2:
            await ctx.send("⚠️ Usage: !os <username>")
            return

        target = parts[1].lstrip("@").strip()
        if not TWITCH_USERNAME_RE.fullmatch(target):
            await ctx.send("⚠️ Invalid username.")
            return

        message = ANTISHOUT_TEMPLATE.format(target=target.lower())
        await ctx.send(message)

# ✅ TwitchIO prep-style loader (used in dynamic imports)
def prepare(bot: commands.Bot):
    if bot.get_cog("Shoutout"):
        print("⚠️ Shoutout already loaded, skipping.")
        return
    bot.add_cog(Shoutout(bot))
