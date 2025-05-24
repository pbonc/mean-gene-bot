import discord
import json
from discord.ext import commands
import asyncio  # For concurrent reaction adds

from bot.utils.wrestlers import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel
from bot.utils import safe_get_guild, safe_get_channel

class RebrandCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_rebrands = {}  # message_id: user_id

    @commands.command(name="rebrand")
    async def rebrand(self, ctx, *, new_name):
        if ctx.channel.name != "dwf-backstage":
            return

        user_id = str(ctx.author.id)
        wrestlers = load_wrestlers()

        if user_id not in wrestlers or "wrestler" not in wrestlers[user_id]:
            await ctx.send("❌ You must have a registered wrestler to rebrand.")
            return

        if "pending_rebrand" in wrestlers[user_id]:
            await ctx.send("🕓 You already have a rebrand pending approval.")
            return

        new_name_lower = new_name.lower()
        if any(data.get("wrestler", "").lower() == new_name_lower for data in wrestlers.values()):
            await ctx.send("⚠️ That name is already taken by another wrestler.")
            return

        guild = ctx.guild
        comm_channel = await safe_get_channel(self.bot, guild, name="dwf-commissioner")
        if not comm_channel:
            await ctx.send("❌ Could not locate the commissioner channel.")
            return

        old_name = wrestlers[user_id]["wrestler"]
        msg = await comm_channel.send(
            f"🔁 `{ctx.author}` requests to rebrand **{old_name}** to **{new_name}**. ✅ to approve, ❌ to reject."
        )

        # Add reactions concurrently to speed up
        await asyncio.gather(
            msg.add_reaction("✅"),
            msg.add_reaction("❌")
        )

        self.pending_rebrands[msg.id] = user_id
        wrestlers[user_id]["pending_rebrand"] = {"from": old_name, "to": new_name}
        save_wrestlers(wrestlers)

        try:
            response = await ctx.send("🔁 Rebrand request submitted for approval.")
            await ctx.message.delete()
            await response.delete()
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # Ignore bot's own reactions
        if payload.user_id == self.bot.user.id:
            return

        # Only handle reactions related to pending rebrands
        if payload.message_id not in self.pending_rebrands:
            return

        user_id = self.pending_rebrands[payload.message_id]
        if payload.user_id != int(user_id):
            # Ignore reactions from users other than the requester
            return

        # Fetch guild and channel safely
        guild = await safe_get_guild(self.bot, payload.guild_id)
        if not guild:
            return

        channel = await safe_get_channel(self.bot, guild, channel_id=payload.channel_id)
        if not channel:
            return

        # Fetch the message to get reaction emoji
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception as e:
            print(f"❌ Failed to fetch message for reaction handling: {e}")
            return

        # Identify emoji name
        emoji = payload.emoji.name

        # Load wrestlers data
        wrestlers = load_wrestlers()
        if user_id not in wrestlers or "pending_rebrand" not in wrestlers[user_id]:
            # No pending rebrand found
            return

        rebrand_info = wrestlers[user_id]["pending_rebrand"]
        old_name = rebrand_info["from"]
        new_name = rebrand_info["to"]

        if emoji == "✅":
            # Approve rebrand
            wrestlers[user_id]["wrestler"] = new_name
            del wrestlers[user_id]["pending_rebrand"]
            save_wrestlers(wrestlers)

            await channel.send(f"✅ Rebrand approved: **{old_name}** is now **{new_name}**.")

        elif emoji == "❌":
            # Reject rebrand
            del wrestlers[user_id]["pending_rebrand"]
            save_wrestlers(wrestlers)

            await channel.send(f"❌ Rebrand rejected: **{old_name}** remains unchanged.")

        else:
            # Ignore other reactions
            return

        # Clean up tracking
        del self.pending_rebrands[payload.message_id]

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        # Optional: Handle reaction removals if needed
        pass

# ✅ Async cog setup
async def setup(bot):
    await bot.add_cog(RebrandCommand(bot))
    print("🧩 RebrandCommand loaded")
