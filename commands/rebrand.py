import discord
import json
from discord.ext import commands
import asyncio
import websockets

from bot.utils.wrestlers import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel
from bot.utils.safe_get_channel import safe_get_channel
from bot.utils.safe_get_guild import safe_get_guild

TICKER_SERVER_URI = "ws://localhost:6789"

async def send_ticker_message(ticker_msg, ticker_uri=TICKER_SERVER_URI):
    try:
        async with websockets.connect(ticker_uri) as websocket:
            msg = {"type": "match_result", "result": ticker_msg}
            await websocket.send(json.dumps(msg))
            print(f"[TickerServer] Sent ticker message: {ticker_msg}")
    except Exception as e:
        print(f"[TickerServer] Could not send ticker message: {e}")

def clean_orphaned_pending_rebrands():
    wrestlers = load_wrestlers()
    cleaned = False
    for uid, data in wrestlers.items():
        if isinstance(data, dict) and "pending_rebrand" in data:
            print(f"🧹 Cleaning orphaned pending_rebrand for user {uid}")
            del data["pending_rebrand"]
            cleaned = True
    if cleaned:
        save_wrestlers(wrestlers)
        print("✅ Cleaned orphaned pending rebrands on startup.")

class RebrandCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_rebrands = {}  # message_id: user_id
        # Clean up on startup!
        clean_orphaned_pending_rebrands()

    @commands.command(name="rebrand")
    async def rebrand(self, ctx, *, new_name):
        print(f"DEBUG: rebrand command called in channel '{ctx.channel.name}' with name '{new_name}'")

        # Only accept in #dwf-backstage
        if ctx.channel.name != "dwf-backstage":
            await ctx.send("❌ This command can only be used in #dwf-backstage.")
            print("DEBUG: Wrong channel, aborting.")
            return

        user_id = str(ctx.author.id)
        wrestlers = load_wrestlers()
        print(f"DEBUG: Loaded wrestlers, user_id: {user_id}")

        if user_id not in wrestlers:
            await ctx.send("❌ You must have a registered wrestler to rebrand. (user_id not found)")
            print("DEBUG: user_id not in wrestlers, aborting.")
            return

        if "wrestler" not in wrestlers[user_id]:
            await ctx.send("❌ You must have a registered wrestler to rebrand. (no 'wrestler' key)")
            print("DEBUG: 'wrestler' not in wrestlers[user_id], aborting.")
            return

        print(f"DEBUG: Wrestler found for user_id: {user_id}: {wrestlers[user_id]['wrestler']}")

        if "pending_rebrand" in wrestlers[user_id]:
            await ctx.send("🕓 You already have a rebrand pending approval.")
            print("DEBUG: Pending rebrand exists, aborting.")
            return

        new_name_lower = new_name.lower()
        for uid, data in wrestlers.items():
            # Only check user entries that are dicts with a 'wrestler' key
            if not isinstance(data, dict) or 'wrestler' not in data:
                continue
            print(f"DEBUG: Checking name for uid {uid}: {data.get('wrestler', '').lower()}")
            if uid != user_id and data.get("wrestler", "").lower() == new_name_lower:
                await ctx.send("⚠️ That name is already taken by another wrestler.")
                print("DEBUG: Name already taken, aborting.")
                return

        guild = ctx.guild
        print(f"DEBUG: Guild is {guild}")

        comm_channel = await safe_get_channel(self.bot, guild, name="dwf-commissioner")
        print(f"DEBUG: Commissioner channel resolved to {comm_channel}")

        if not comm_channel:
            await ctx.send("❌ Could not locate the commissioner channel.")
            print("DEBUG: Could not locate the commissioner channel, aborting.")
            return

        old_name = wrestlers[user_id]["wrestler"]
        try:
            msg = await comm_channel.send(
                f"🔁 A wrestler requests to rebrand **{old_name}** to **{new_name}**. ✅ to approve, ❌ to reject."
            )
            print(f"DEBUG: Sent message to commissioner channel: {msg}")
        except Exception as e:
            await ctx.send("❌ Failed to send message to commissioner channel.")
            print(f"DEBUG: Exception when sending to commissioner channel: {e}")
            return

        try:
            await asyncio.gather(
                msg.add_reaction("✅"),
                msg.add_reaction("❌")
            )
            print("DEBUG: Added reactions to commissioner message.")
        except Exception as e:
            print(f"DEBUG: Could not add reactions: {e}")

        self.pending_rebrands[msg.id] = user_id
        wrestlers[user_id]["pending_rebrand"] = {"from": old_name, "to": new_name}
        save_wrestlers(wrestlers)
        print("DEBUG: Saved wrestlers with pending rebrand.")

        try:
            await ctx.message.delete()
            print("DEBUG: Deleted user message in backstage.")
        except discord.Forbidden:
            print("DEBUG: Forbidden to delete message.")
        except Exception as e:
            print(f"DEBUG: Error deleting message: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # Ignore bot's own reactions
        if payload.user_id == self.bot.user.id:
            return

        if payload.message_id not in self.pending_rebrands:
            return

        guild = await safe_get_guild(self.bot, payload.guild_id)
        if not guild:
            print("DEBUG: Could not fetch guild in on_raw_reaction_add.")
            return

        user = guild.get_member(payload.user_id)
        if not user:
            print("DEBUG: Could not fetch user in on_raw_reaction_add.")
            return

        # Only users with "commish", "commissioner", "marvin", or the server owner can approve/reject
        is_commissioner = any(
            "commish" in r.name.lower() or
            "commissioner" in r.name.lower() or
            "marvin" in r.name.lower()
            for r in user.roles
        )
        is_owner = user.id == guild.owner_id

        if not (is_commissioner or is_owner):
            print(f"User {user} is not a commissioner, Marvin, or owner, ignoring reaction.")
            return

        channel = await safe_get_channel(self.bot, guild, channel_id=payload.channel_id)
        if not channel:
            print("DEBUG: Could not fetch channel in on_raw_reaction_add.")
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception as e:
            print(f"❌ Failed to fetch message for reaction handling: {e}")
            return

        emoji = payload.emoji.name

        user_id = self.pending_rebrands[payload.message_id]
        wrestlers = load_wrestlers()
        if user_id not in wrestlers or "pending_rebrand" not in wrestlers[user_id]:
            print("DEBUG: No pending rebrand for user in on_raw_reaction_add.")
            return

        rebrand_info = wrestlers[user_id]["pending_rebrand"]
        old_name = rebrand_info["from"]
        new_name = rebrand_info["to"]

        backstage_channel = await safe_get_channel(self.bot, guild, name="dwf-backstage")
        twitch_channel = get_twitch_channel()

        if emoji == "✅":
            wrestlers[user_id]["wrestler"] = new_name
            del wrestlers[user_id]["pending_rebrand"]
            save_wrestlers(wrestlers)

            approve_msg = f"✅ Rebrand approved: **{old_name}** is now **{new_name}**!"

            await channel.send(approve_msg)
            if backstage_channel:
                await backstage_channel.send(approve_msg)
            if twitch_channel:
                await twitch_channel.send(f"🔁 {old_name} is now known as {new_name}!")
            await send_ticker_message(f"{old_name} is now known as {new_name}!")
            print("DEBUG: Rebrand approved and broadcasted.")

        elif emoji == "❌":
            del wrestlers[user_id]["pending_rebrand"]
            save_wrestlers(wrestlers)

            reject_msg = f"❌ Rebrand rejected: **{old_name}** remains unchanged."

            await channel.send(reject_msg)
            if backstage_channel:
                await backstage_channel.send(reject_msg)
            if twitch_channel:
                await twitch_channel.send(f"❌ {old_name}'s rebrand was rejected!")
            await send_ticker_message(f"Rebrand rejected for {old_name}.")
            print("DEBUG: Rebrand rejected and broadcasted.")

        else:
            print("DEBUG: Reaction is not approve or reject, ignoring.")
            return

        del self.pending_rebrands[payload.message_id]
        print("DEBUG: Cleared pending rebrand from memory.")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        pass  # Optionally handle reaction removals

async def setup(bot):
    await bot.add_cog(RebrandCommand(bot))
    print("🧩 RebrandCommand loaded")