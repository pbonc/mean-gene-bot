import os
import random
import glob
from twitchio.ext import commands
from bot.sfx_player import queue_sfx, get_worst_sfx

SFX_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sfx"))

class WorstSFX(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("🐢 WorstSFX Cog initialized")

    @commands.command(name="worstsfx")
    async def worstsfx(self, ctx: commands.Context):
        if not os.path.exists(SFX_FOLDER):
            await ctx.send("❌ SFX folder not found.")
            return

        worst_path = get_worst_sfx(SFX_FOLDER)
        if not worst_path:
            await ctx.send("⚠️ No SFX files available.")
            return

        cmd = os.path.splitext(os.path.basename(worst_path))[0]
        safe_cmd = ''.join(c for c in cmd if c.isalnum())  # sanitize for Twitch
        print(f"🐢 {ctx.author.name} triggered !worstsfx → !{cmd}")

        await queue_sfx(worst_path)
        await ctx.send(f"!{safe_cmd}")

# ✅ TwitchIO cog loader
def prepare(bot: commands.Bot):
    if bot.get_cog("WorstSFX"):
        print("⚠️ WorstSFX already loaded, skipping.")
        return
    bot.add_cog(WorstSFX(bot))
