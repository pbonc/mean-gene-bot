from twitchio.ext import commands
from bot.data.command_loader import load_sfx_commands

class SFXRefresh(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sfxrefresh")
    async def sfxrefresh(self, ctx):
        if not ctx.author.is_mod:
            return

        try:
            # Clear only previously loaded SFX commands
            for name in list(self.bot.commands):
                if name not in {"sfxrefresh", "botver"}:
                    del self.bot.commands[name]

            load_sfx_commands(self.bot, verbose=True)
            await ctx.send("🔄 SFX commands refreshed.")
        except Exception as e:
            await ctx.send("⚠️ SFX refresh failed.")
            print(f"❌ SFX refresh error: {e}")
