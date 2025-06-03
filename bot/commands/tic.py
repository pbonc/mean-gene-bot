import os
import random
import logging
from twitchio.ext import commands
from .base_command import mod_only

# Set the tic file location to assets/txt/tic.txt at the project root
TIC_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "txt", "tic.txt")
)

class TicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = TIC_FILE
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.isfile(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write("")
        self.logger = logging.getLogger("tic")

    @commands.command(name="tic")
    async def tic(self, ctx: commands.Context):
        """Handles !tic [add <text>|<number>]"""
        parts = ctx.message.content.split(maxsplit=2)

        if len(parts) == 1:
            await self._send_random(ctx)
        elif parts[1].lower() == "add":
            await self._cmd_add(ctx, parts)
        elif parts[1].isdigit():
            await self._send_by_index(ctx, int(parts[1]) - 1)
        else:
            await ctx.send("❌ Usage: !tic, !tic <number>, !tic add <text>")

    async def _send_random(self, ctx):
        tics = self._load()
        if not tics:
            await ctx.send("🫠 No tics found.")
            return
        await ctx.send(f"🔔 Tic: \"{random.choice(tics)}\"")

    async def _send_by_index(self, ctx, idx):
        tics = self._load()
        if 0 <= idx < len(tics):
            await ctx.send(f"📘 Tic #{idx + 1}: \"{tics[idx]}\"")
        else:
            await ctx.send(f"❌ No tic at #{idx + 1}.")

    @mod_only
    async def _cmd_add(self, ctx, parts):
        if len(parts) < 3 or not parts[2].strip():
            await ctx.send("⚠️ Usage: !tic add <text>")
            return
        text = parts[2].strip()
        tics = self._load()
        if text in tics:
            await ctx.send("⚠️ That tic already exists.")
            return
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        await ctx.send(f"✅ Added tic #{len(tics) + 1}: \"{text}\"")
        self.logger.info(f"Tic added by {ctx.author.name}: {text}")

    def _load(self):
        if not os.path.isfile(self.file_path):
            return []
        with open(self.file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

def prepare(bot):
    if not bot.get_cog("TicCog"):
        bot.add_cog(TicCog(bot))