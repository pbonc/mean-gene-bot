import discord
from discord.ext import commands
import json
from pathlib import Path

from bot.mgb_dwf import load_wrestlers

class PromoCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="promo")
    async def promo(self, ctx, *, message_text):
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ This command can only be used in the #dwf-backstage channel.")
            return

        if ctx.channel.name != "dwf-backstage":
            return

        wrestler_name = self.get_registered_name(ctx.author.id)
        if not wrestler_name:
            await ctx.send("❌ You must register a persona before submitting a promo.")
            return

        comm_channel = discord.utils.get(ctx.guild.text_channels, name="dwf-commissioner")
        if comm_channel:
            msg = await comm_channel.send(
                f"🎤 Promo submitted by **{wrestler_name}**:\n\n> {message_text}"
            )
            print(f"✅ Promo sent to commissioner: {msg.jump_url}")
        else:
            await ctx.send("⚠️ Commissioner channel not found.")
            return

        self.save_promo(ctx.author.id, wrestler_name, message_text)
        await ctx.send("✅ Promo submitted!")

    def get_registered_name(self, user_id):
        wrestlers = load_wrestlers()
        record = wrestlers.get(str(user_id), {})
        return record.get("wrestler")

    def save_promo(self, user_id, name, message):
        path = Path("data/promos_pending.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        promos = []
        if path.exists():
            try:
                with open(path, "r") as f:
                    promos = json.load(f)
            except Exception:
                promos = []

        promos.append({"user_id": str(user_id), "name": name, "message": message})
        with open(path, "w") as f:
            json.dump(promos, f, indent=2)

# ✅ Proper async setup function
async def setup(bot):
    await bot.add_cog(PromoCommand(bot))