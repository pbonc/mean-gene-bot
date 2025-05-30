import os
import random
import logging
from twitchio.ext import commands

# Always use tic.txt in the src/data directory (relative to this file)
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SRC_DIR, "..", "data")
DATA_DIR = os.path.abspath(DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
TIC_FILE = os.path.join(DATA_DIR, "tic.txt")

class TicCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = TIC_FILE
        if not os.path.isfile(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write("")
        self.logger = logging.getLogger("tic")

    @commands.command(name="tic")
    async def tic(self, ctx: commands.Context):
        """Show a random tic, a specific one, or add a new one (mods only)."""
        parts = ctx.message.content.split(maxsplit=2)

        if len(parts) == 1:
            # !tic
            await self.send_random_tic(ctx)

        elif parts[1].lower() == "add":
            if not (hasattr(ctx.author, "is_mod") and ctx.author.is_mod):
                await ctx.send("❌ Only mods can add tics.")
                return
            if len(parts) < 3:
                await ctx.send("⚠️ Usage: !tic add <text>")
                return
            new_tic = parts[2].strip()
            if not new_tic:
                await ctx.send("⚠️ Cannot add empty tic.")
                return
            await self.add_tic(ctx, new_tic)

        elif parts[1].isdigit():
            index = int(parts[1]) - 1  # 1-based input
            await self.send_tic_by_index(ctx, index)
        else:
            await ctx.send("❌ Invalid usage. Try !tic, !tic 12, or !tic add <text>")

    async def send_random_tic(self, ctx):
        tics = self.load_tics()
        if not tics:
            await ctx.send("🫠 No tics found.")
            return
        quote = random.choice(tics)
        await ctx.send(f"🔔 Tic: \"{quote}\"")

    async def send_tic_by_index(self, ctx, index):
        tics = self.load_tics()
        if 0 <= index < len(tics):
            await ctx.send(f"📘 Tic #{index + 1}: \"{tics[index]}\"")
        else:
            await ctx.send(f"❌ No tic at #{index + 1}.")

    async def add_tic(self, ctx, text):
        tics = self.load_tics()
        if text in tics:
            await ctx.send("⚠️ That tic already exists.")
            return
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(f"{text}\n")
        await ctx.send(f"✅ Added tic #{len(tics) + 1}: \"{text}\"")
        self.logger.info(f"Tic added by {ctx.author.name}: {text}")

    def load_tics(self):
        if not os.path.isfile(self.file_path):
            return []
        with open(self.file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

def prepare(bot):
    if not bot.get_cog("TicCog"):
        bot.add_cog(TicCog(bot))