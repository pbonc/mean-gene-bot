import discord
import json
from pathlib import Path
from discord.ext import commands
import aiofiles  # For async file IO

from bot.mgb_dwf import load_wrestlers
from bot.utils import safe_get_channel

class PromoCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="promo")
    async def promo(self, ctx, *, message_text: str):
        """
        Submit a promo for commissioner review. Only works in #dwf-backstage.
        """
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ This command can only be used in the #dwf-backstage channel.")
            return

        if ctx.channel.name != "dwf-backstage":
            return

        wrestler_name = self.get_registered_name(ctx.author.id)
        if not wrestler_name:
            await ctx.send("❌ You must register a persona before submitting a promo.")
            return

        comm_channel = await safe_get_channel(self.bot, ctx.guild, name="dwf-commissioner")
        if comm_channel is None:
            await ctx.send("⚠️ Commissioner channel not found.")
            return

        try:
            msg = await comm_channel.send(
                f"🎤 Promo submitted by **{wrestler_name}**:\n\n> {message_text}"
            )
            print(f"✅ Promo sent to commissioner: {msg.jump_url}")
        except Exception as e:
            await ctx.send("❌ Failed to send promo to commissioner channel.")
            print(f"⚠️ Error sending promo: {e}")
            return

        await self.save_promo(ctx.author.id, wrestler_name, message_text)
        await ctx.send("✅ Promo submitted!")

    def get_registered_name(self, user_id: int) -> str | None:
        wrestlers = load_wrestlers()
        record = wrestlers.get(str(user_id), {})
        return record.get("wrestler")

    async def save_promo(self, user_id: int, name: str, message: str):
        """
        Save the promo to data/promos_pending.json asynchronously.
        """
        path = Path("data/promos_pending.json")
        path.parent.mkdir(parents=True, exist_ok=True)

        promos = []
        if path.exists():
            try:
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    promos = json.loads(content)
            except Exception as e:
                print(f"⚠️ Failed to load existing promos: {e}")
                promos = []

        promos.append({
            "user_id": str(user_id),
            "name": name,
            "message": message
        })

        try:
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(promos, indent=2))
        except Exception as e:
            print(f"⚠️ Failed to save promos: {e}")

# ✅ Async cog setup
async def setup(bot):
    await bot.add_cog(PromoCommand(bot))
    print("🧩 PromoCommand loaded")
