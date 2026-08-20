"""The !icyhot emote-wall command."""

from twitchio.ext import commands


TWITCH_MESSAGE_LIMIT = 500
ICY_EMOTE = "iamdarIcy"


def icyhot_message(limit=TWITCH_MESSAGE_LIMIT):
    """Fill a chat message with the most space-separated emotes that fit."""
    count = (limit + 1) // (len(ICY_EMOTE) + 1)
    return " ".join([ICY_EMOTE] * count)


class IcyHotCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="icyhot")
    async def icyhot(self, ctx):
        await ctx.send(icyhot_message())


def prepare(bot):
    if not bot.get_cog("IcyHotCog"):
        bot.add_cog(IcyHotCog(bot))
