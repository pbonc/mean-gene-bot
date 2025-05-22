import random
import discord
import json
from discord.ext import commands
from bot.mgb_dwf import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel
from bot.utils import safe_get_guild, safe_get_channel
from datetime import datetime
import asyncio  # For concurrent reaction adds

class RegisterCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_messages = {}  # message_id: (user_id, wrestler_name)

    @staticmethod
    def clean_orphaned_registrations():
        wrestlers = load_wrestlers()
        original_count = len(wrestlers)

        cleaned = {
            uid: data
            for uid, data in wrestlers.items()
            if not ("pending" in data and "wrestler" not in data)
        }

        removed = original_count - len(cleaned)
        if removed > 0:
            save_wrestlers(cleaned)
            print(f"✩ Removed {removed} orphaned pending registrations.")
        else:
            print("✅ No orphaned pending registrations found.")

    @commands.command(name="register")
    async def register(self, ctx, *, wrestler_name):
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ You must use this command in the #dwf-backstage channel.")
            return

        if ctx.channel.name != "dwf-backstage":
            return

        wrestlers = load_wrestlers()
        user_id = str(ctx.author.id)

        if user_id in wrestlers:
            if "wrestler" in wrestlers[user_id]:
                await ctx.send("You’ve already registered a persona.")
                return
            if "pending" in wrestlers[user_id]:
                await ctx.send("You already have a registration pending approval.")
                return

        existing_names = [w.get("wrestler") for w in wrestlers.values() if "wrestler" in w]
        if wrestler_name in existing_names:
            await ctx.send("That name is already taken.")
            return

        guild = ctx.guild
        comm_channel = await safe_get_channel(self.bot, guild, name="dwf-commissioner")
        if not comm_channel:
            await ctx.send("❌ Could not locate the commissioner channel.")
            return

        msg = await comm_channel.send(
            f"📝 `{ctx.author}` requests to register as **{wrestler_name}**. ✅ to approve, ❌ to reject."
        )

        self.pending_messages[msg.id] = (user_id, wrestler_name)
        wrestlers[user_id] = {"pending": wrestler_name}
        save_wrestlers(wrestlers)

        # Reaction adds concurrently
        await asyncio.gather(
            msg.add_reaction("✅"),
            msg.add_reaction("❌")
        )

        try:
            response = await ctx.send("✅ Registration request submitted for approval.")
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

        guild = await safe_get_guild(self.bot, payload.guild_id)
        if guild is None:
            return

        try:
            member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        except Exception:
            return

        if not (member.guild_permissions.manage_messages or member.guild_permissions.administrator):
            return

        channel = await safe_get_channel(self.bot, guild, channel_id=payload.channel_id)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        wrestlers = load_wrestlers()
        print(f"🐛 Loaded wrestlers: {json.dumps(wrestlers, indent=2)}")
        user_id = None
        wrestler_name = None

        for uid, data in wrestlers.items():
            if "pending" in data and f"**{data['pending']}**" in message.content:
                user_id = uid
                wrestler_name = data["pending"]
                break

        if not user_id:
            return

        if str(payload.emoji) == "✅":
            try:
                registrant = await guild.fetch_member(int(user_id))
                registrant_tag = f"{registrant.name}#{registrant.discriminator}"
            except:
                registrant_tag = "Unknown#0000"

            approver_tag = f"{member.name}#{member.discriminator}"

            wrestlers[user_id] = {
                "wrestler": wrestler_name,
                "record": {"wins": 0, "losses": 0},
                "debut": datetime.utcnow().isoformat() + "Z",
                "style": "unknown",
                "registered_by": {"id": user_id, "tag": registrant_tag},
                "approved_by": approver_tag,
                "title_history": [],
                "current_title": None
            }

            backstage = await safe_get_channel(self.bot, guild, name="dwf-backstage")
            if backstage:
                await backstage.send(f"📢 **{wrestler_name}** has just signed a new contract with the DWF!")

            twitch_channel = get_twitch_channel()
            if twitch_channel:
                await twitch_channel.send(f"📢 {wrestler_name} has officially signed with the DWF!")

            try:
                user = await self.bot.fetch_user(int(user_id))
                await user.send(f"🎉 Your persona **{wrestler_name}** has been approved and you're now part of the DWF!")
            except:
                pass

        else:
            wrestlers.pop(user_id, None)
            await message.reply(f"❌ {wrestler_name} was rejected.")

        save_wrestlers(wrestlers)

# ✅ Async cog setup
async def setup(bot):
    RegisterCommand.clean_orphaned_registrations()
    cog = RegisterCommand(bot)
    await bot.add_cog(cog)
