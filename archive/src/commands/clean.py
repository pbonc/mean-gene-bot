import discord
from discord.ext import commands
import asyncio

from bot.utils.safe_get_channel import safe_get_channel
from bot.utils.safe_get_guild import safe_get_guild

CHANNELS = {
    "🕶️": "dwf-backstage",
    "🏛️": "dwf-commissioner",
    "📢": "dwf-promos"
}

PERMITTED_ROLES = ["commish", "commissioner", "marvin"]

class CleanCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.clean_message_id = None

    @commands.command(name="clean")
    async def clean(self, ctx):
        # Only allow in dwf-commissioner
        print(f"[DEBUG] !clean command invoked in #{ctx.channel.name} by {ctx.author}")
        if ctx.channel.name != "dwf-commissioner":
            await ctx.send("❌ This command can only be used in #dwf-commissioner.")
            print(f"[DEBUG] !clean command not in commissioner, abort.")
            return

        desc = "\n".join([f"{emoji} — {name.replace('dwf-', '').capitalize()}" for emoji, name in CHANNELS.items()])
        msg = await ctx.send(f"**Select a reaction to clean a channel:**\n{desc}")
        print(f"[DEBUG] Clean selection message sent: {msg.id}")
        self.clean_message_id = msg.id

        # Add reactions
        for emoji in CHANNELS:
            await msg.add_reaction(emoji)
            print(f"[DEBUG] Added reaction {emoji}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        print(f"[DEBUG] on_raw_reaction_add fired for message {payload.message_id} by user {payload.user_id} with emoji {payload.emoji.name}")

        # Only respond to reaction on our message
        if payload.message_id != self.clean_message_id:
            print(f"[DEBUG] Ignored reaction: not our clean message ({self.clean_message_id})")
            return

        guild = await safe_get_guild(self.bot, payload.guild_id)
        if not guild:
            print(f"[DEBUG] Could not fetch guild {payload.guild_id}")
            return
        user = guild.get_member(payload.user_id)
        if not user:
            print(f"[DEBUG] Could not fetch user {payload.user_id}")
            return
        if user.bot:
            print(f"[DEBUG] Ignored reaction from bot user {user}")
            return

        print(f"[DEBUG] User {user} roles: {[r.name for r in user.roles]}")
        is_commissioner = any(
            any(role in r.name.lower() for role in PERMITTED_ROLES)
            for r in user.roles
        )
        is_owner = user.id == guild.owner_id
        print(f"[DEBUG] is_commissioner: {is_commissioner}, is_owner: {is_owner}")

        if not (is_commissioner or is_owner):
            print(f"[DEBUG] User {user} is not permitted to clean channels, ignoring reaction.")
            return

        emoji = payload.emoji.name
        if emoji not in CHANNELS:
            print(f"[DEBUG] Emoji {emoji} not in CHANNELS map, ignoring.")
            return

        channel_name = CHANNELS[emoji]
        print(f"[DEBUG] Cleaning channel: {channel_name}")
        channel = await safe_get_channel(self.bot, guild, name=channel_name)
        if not channel:
            print(f"[DEBUG] Could not find channel {channel_name}")
            await self._send_dm(user, f"Could not find channel `{channel_name}`.")
            return

        await self._clean_channel(channel)
        comm_channel = await safe_get_channel(self.bot, guild, name="dwf-commissioner")
        if comm_channel:
            await comm_channel.send(f"🧹 {user.display_name} cleaned #{channel.name}.")
        print(f"[DEBUG] Completed cleaning for #{channel.name}")

    async def _clean_channel(self, channel):
        # Optionally skip pinned messages
        def not_pinned(m): return not m.pinned

        deleted = await channel.purge(limit=1000, check=not_pinned)
        print(f"[DEBUG] Cleaned {len(deleted)} messages in {channel.name}")

    async def _send_dm(self, user, text):
        try:
            await user.send(text)
            print(f"[DEBUG] Sent DM to {user}: {text}")
        except Exception as e:
            print(f"[DEBUG] Failed to send DM to {user}: {e}")

async def setup(bot):
    await bot.add_cog(CleanCommand(bot))
    print("🧩 CleanCommand loaded")