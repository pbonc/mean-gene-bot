# commands/promo.py

import discord
import json
from pathlib import Path
from discord.ext import commands

from bot import load_wrestlers

PROMO_FILE = Path(__file__).parent.parent / "data" / "promos_pending.json"
PROMO_FILE.parent.mkdir(parents=True, exist_ok=True)
if not PROMO_FILE.exists():
    PROMO_FILE.write_text("{}")

class PromoCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="promo")
    async def promo(self, ctx, *, message_text):
        if ctx.channel.name != "dwf-promos":
            return

        wrestlers = load_wrestlers()
        user_id = str(ctx.author.id)

        if user_id not in wrestlers or "wrestler" not in wrestlers[user_id]:
            await ctx.send("❌ You must be a registered wrestler to cut a promo.")
            return

        wrestler_name = wrestlers[user_id]["wrestler"]
        comm_channel = discord.utils.get(ctx.guild.text_channels, name="dwf-commissioner")
        if not comm_channel:
            await ctx.send("❌ Could not find the commissioner channel.")
            return

        formatted_message = (
            f"🎤 Promo submitted by **{wrestler_name}**:\n\n> {message_text.strip()}\n\n"
            "✅ to broadcast, ❌ to discard."
        )
        msg = await comm_channel.send(formatted_message)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        # Store pending promo
        try:
            with PROMO_FILE.open("r") as f:
                pending_promos = json.load(f)
        except json.JSONDecodeError:
            pending_promos = {}

        pending_promos[str(msg.id)] = {
            "author": wrestler_name,
            "text": message_text.strip(),
        }

        with PROMO_FILE.open("w") as f:
            json.dump(pending_promos, f, indent=2)

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            print("⚠️ Missing permissions to delete promo message.")

def setup(bot):
    bot.add_cog(PromoCommand(bot))
