import discord
from discord.ext import commands
import json
from pathlib import Path

from bot import announce_new_wrestler, set_twitch_channel
from bot import load_wrestlers, save_wrestlers

class RegisterCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="register")
    async def register(self, ctx, *, wrestler_name):
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ You must use this command in the #dwf-backstage channel.")
            return

        if ctx.channel.name != "dwf-backstage":
            return

        wrestlers = load_wrestlers()
        user_id = str(ctx.author.id)

        if user_id in wrestlers and "wrestler" in wrestlers[user_id]:
            await ctx.send("You’ve already registered a persona.")
            return

        if user_id in wrestlers and "pending" in wrestlers[user_id]:
            await ctx.send("You already have a registration pending approval.")
            return

        if wrestler_name in [w.get("wrestler") for w in wrestlers.values() if "wrestler" in w]:
            await ctx.send("That name is already taken.")
            return

        comm_channel = discord.utils.get(ctx.guild.text_channels, name="dwf-commissioner")
        if not comm_channel:
            await ctx.send("Could not locate the commissioner channel.")
            return

        msg = await comm_channel.send(
            f"📝 `{ctx.author}` requests to register as **{wrestler_name}**. ✅ to approve, ❌ to reject."
        )
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        wrestlers[user_id] = {"pending": wrestler_name}
        save_wrestlers(wrestlers)

        response = await ctx.send("Registration request submitted for approval.")
        try:
            await ctx.message.delete()
            await response.delete()
        except discord.Forbidden:
            print("⚠️ Missing permissions to delete registration message.")

def setup(bot):
    bot.add_cog(RegisterCommand(bot))
