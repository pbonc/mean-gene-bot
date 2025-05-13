import random
import discord
from discord.ext import commands
from bot.mgb_dwf import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel

MATCH_COMMAND_VERSION = "v1.0.0a"

class MatchCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="match")
    async def match(self, ctx):
        if ctx.channel.name != "dwf-commissioner":
            return

        wrestlers = load_wrestlers()
        active_wrestlers = [w["wrestler"] for w in wrestlers.values() if "wrestler" in w]

        if len(active_wrestlers) < 2:
            await ctx.send("❌ Not enough registered wrestlers for a match.")
            return

        fighter1, fighter2 = random.sample(active_wrestlers, 2)
        winner = random.choice([fighter1, fighter2])
        loser = fighter2 if winner == fighter1 else fighter1

        # Update records
        for uid, data in wrestlers.items():
            if data.get("wrestler") == winner:
                data["record"]["wins"] += 1
            elif data.get("wrestler") == loser:
                data["record"]["losses"] += 1

        save_wrestlers(wrestlers)

        twitch_channel = get_twitch_channel()
        if twitch_channel:
            await twitch_channel.send(f"🥊 It's time for a match!")
            await twitch_channel.send(f"👊 {fighter1} VS {fighter2}!")
            await twitch_channel.send("🥁 The crowd goes silent...")
            await twitch_channel.send(f"🏆 **{winner}** wins the match!")

        # Backstage summary
        backstage = discord.utils.get(ctx.guild.text_channels, name="dwf-backstage")
        if backstage:
            await backstage.send(
                f"📊 Match Result: **{winner}** defeated **{loser}**!"
            )

# ✅ Async cog setup
async def setup(bot):
    await bot.add_cog(MatchCommand(bot))
    print(f"🧩 MatchCommand loaded (version {MATCH_COMMAND_VERSION})")
