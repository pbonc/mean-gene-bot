import discord
import json
from discord.ext import commands
from bot.mgb_dwf import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel

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
        print(f"🐛 Loaded wrestlers: {json.dumps(wrestlers, indent=2)}")

        if user_id not in wrestlers or "wrestler" not in wrestlers[user_id]:
            await ctx.send("❌ You must have a registered wrestler to rebrand.")
            return

        if "pending_rebrand" in wrestlers[user_id]:
            await ctx.send("🕓 You already have a rebrand pending approval.")
            return

        new_name_lower = new_name.lower()
        if any(
            data.get("wrestler", "").lower() == new_name_lower
            for uid, data in wrestlers.items()
        ):
            await ctx.send("⚠️ That name is already taken by another wrestler.")
            return

        comm_channel = discord.utils.get(ctx.guild.text_channels, name="dwf-commissioner")
        if not comm_channel:
            await ctx.send("❌ Could not locate the commissioner channel.")
            return

        old_name = wrestlers[user_id]["wrestler"]
        msg = await comm_channel.send(
            f"🔁 `{ctx.author}` requests to rebrand **{old_name}** to **{new_name}**. ✅ to approve, ❌ to reject."
        )

        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

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
        if payload.user_id == self.bot.user.id:
            return
        if str(payload.emoji) not in {"✅", "❌"}:
            return
        if payload.message_id not in self.pending_rebrands:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        if not (member.guild_permissions.manage_messages or member.guild_permissions.administrator):
            return

        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        user_id = self.pending_rebrands.pop(payload.message_id)
        wrestlers = load_wrestlers()

        if user_id not in wrestlers or "pending_rebrand" not in wrestlers[user_id]:
            return

        from_name = wrestlers[user_id]["pending_rebrand"]["from"]
        to_name = wrestlers[user_id]["pending_rebrand"]["to"]

        if str(payload.emoji) == "✅":
            wrestlers[user_id]["wrestler"] = to_name
            del wrestlers[user_id]["pending_rebrand"]

            backstage = discord.utils.get(guild.text_channels, name="dwf-backstage")
            if backstage:
                await backstage.send(f"🎭 **{from_name}** has rebranded! From now on, they are known as **{to_name}**!")

            twitch_channel = get_twitch_channel()
            if twitch_channel:
                await twitch_channel.send(f"🎭 {from_name} has rebranded into **{to_name}** in the DWF!")

            try:
                user = await self.bot.fetch_user(int(user_id))
                await user.send(f"✅ Your rebrand to **{to_name}** has been approved!")
            except:
                pass

            await message.reply(f"✅ Rebrand approved: {from_name} → {to_name}")
        else:
            del wrestlers[user_id]["pending_rebrand"]
            await message.reply(f"❌ Rebrand rejected for {from_name}.")

        save_wrestlers(wrestlers)

# ✅ Async cog setup
async def setup(bot):
    await bot.add_cog(RebrandCommand(bot))
    print("🧩 RebrandCommand loaded")
