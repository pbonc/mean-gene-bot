import os
import random
import logging
from twitchio.ext import commands
from .base_command import mod_only

# Set the derpism file location to assets/txt/derpisms.txt at the project root
DERPISM_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "txt", "derpisms.txt")
)

class DerpismCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = DERPISM_FILE
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.isfile(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write("")
        self.logger = logging.getLogger("derpism")

    @commands.command(name="derpism")
    async def derpism(self, ctx: commands.Context):
        """Handles !derpism [add <text>|<number>]"""
        parts = ctx.message.content.split(maxsplit=2)

        if len(parts) == 1:
            await self._send_random(ctx)
        elif parts[1].lower() == "add":
            await self._cmd_add(ctx, parts)
        elif parts[1].isdigit():
            await self._send_by_index(ctx, int(parts[1]) - 1)
        else:
            await ctx.send("❌ Usage: !derpism, !derpism <number>, !derpism add <text>")

    async def _send_random(self, ctx):
        derpisms = self._load()
        if not derpisms:
            await ctx.send("🫠 No derpisms found.")
            return
        await ctx.send(f"🌀 Derpism: \"{random.choice(derpisms)}\"")

    async def _send_by_index(self, ctx, idx):
        derpisms = self._load()
        if 0 <= idx < len(derpisms):
            await ctx.send(f"📘 Derpism #{idx + 1}: \"{derpisms[idx]}\"")
        else:
            await ctx.send(f"❌ No derpism at #{idx + 1}.")

    @mod_only
    async def _cmd_add(self, ctx, parts):
        if len(parts) < 3 or not parts[2].strip():
            await ctx.send("⚠️ Usage: !derpism add <text>")
            return
        text = parts[2].strip()
        derpisms = self._load()
        if text in derpisms:
            await ctx.send("⚠️ That derpism already exists.")
            return
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        await ctx.send(f"✅ Added derpism #{len(derpisms) + 1}: \"{text}\"")
        self.logger.info(f"Derpism added by {ctx.author.name}: {text}")

    def _load(self):
        if not os.path.isfile(self.file_path):
            return []
        with open(self.file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

def prepare(bot):
    if not bot.get_cog("DerpismCog"):
        bot.add_cog(DerpismCog(bot))