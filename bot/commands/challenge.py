import discord
from discord.ext import commands
from bot.mgb_dwf import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel
import random

CHALLENGE_COMMAND_VERSION = "v1.0.0a"

class ChallengeCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_challenges = {}  # message_id -> challenger_id

    @commands.command(name="challenge")
    async def challenge(self, ctx):
        if ctx.channel.name != "dwf-backstage":
            return

        wrestlers = load_wrestlers()
        challenger_id = str(ctx.author.id)
        challenger_data = wrestlers.get(challenger_id)

        if not challenger_data or "wrestler" not in challenger_data:
            await ctx.send("❌ You must be a registered wrestler to issue a challenge.")
            return

        challenger_name = challenger_data["wrestler"]

        msg = await ctx.send(f"🔥 **{challenger_name}** has issued an open challenge! React with ✅ to accept!")
        await msg.add_reaction("✅")
        self.active_challenges[msg.id] = challenger_id

        # Twitch + backstage announcements
        twitch_channel = get_twitch_channel()
        if twitch_channel:
            await twitch_channel.send(f"🔥 {challenger_name} has issued an open challenge!")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) != "✅":
            return

        message_id = payload.message_id
        if message_id not in self.active_challenges:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        challenger_id = self.active_challenges[message_id]
        if str(payload.user_id) == challenger_id:
            return  # Challenger can't accept their own challenge

        wrestlers = load_wrestlers()

        challenger = wrestlers.get(challenger_id)
        reactor = wrestlers.get(str(payload.user_id))

        if not challenger or "wrestler" not in challenger:
            return

        if not reactor or "wrestler" not in reactor:
            return

        challenger_name = challenger["wrestler"]
        reactor_name = reactor["wrestler"]

        fighter1, fighter2 = challenger_name, reactor_name
        winner = random.choice([fighter1, fighter2])
        loser = fighter2 if winner == fighter1 else fighter1

        # Update records
        for uid, data in wrestlers.items():
            if data.get("wrestler") == winner:
                data["record"]["wins"] += 1
            elif data.get("wrestler") == loser:
                data["record"]["losses"] += 1

        save_wrestlers(wrestlers)
        print("💾 Wrestlers saved.")

        twitch_channel = get_twitch_channel()
        if twitch_channel:
            await twitch_channel.send(f"🎯 Challenge accepted! {fighter1} vs {fighter2}!")
            await twitch_channel.send("🥁 The battle begins...")
            await twitch_channel.send(f"🏆 **{winner}** wins the match!")

        backstage = discord.utils.get(guild.text_channels, name="dwf-backstage")
        if backstage:
            await backstage.send(f"📊 Match Result: **{winner}** defeated **{loser}** in a challenge match!")

        # Clean up this challenge
        del self.active_challenges[message_id]

# ✅ Async cog setup
async def setup(bot):
    await bot.add_cog(ChallengeCommand(bot))
    print(f"🧩 ChallengeCommand loaded (version {CHALLENGE_COMMAND_VERSION})")