print("📦 debug_clean.py imported")

from discord.ext import commands

class DebugClean(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="clean", aliases=["clear"])
    async def clean(self, ctx):
        await ctx.send("✅ Clean command loaded and triggered.")

async def setup(bot):
    print("🧹 debug_clean.py setup() called")
    await bot.add_cog(DebugClean(bot))
