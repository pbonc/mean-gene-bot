import os
import random
import logging
from twitchio.ext import commands

DERPISM_FILE = "data/derpisms.txt"

class DerpismCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        print("DerpismCog __init__ called; id(self):", id(self), "id(bot):", id(bot))  # DEBUG
        self.bot = bot
        self.file_path = DERPISM_FILE
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.isfile(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write("")
        self.logger = logging.getLogger("derpism")

    @commands.command(name="derpism")
    async def derpism(self, ctx: commands.Context):
        print("derpism command handler called; id(self):", id(self), "id(self.bot):", id(self.bot))  # DEBUG
        print("ctx.author:", ctx.author.name, "| ctx.content:", ctx.message.content)
        """Show a random derpism, a specific one, or add a new one (mods only)."""
        parts = ctx.message.content.split(maxsplit=2)

        if len(parts) == 1:
            # !derpism
            await self.send_random_derpism(ctx)

        elif parts[1].lower() == "add":
            if not (hasattr(ctx.author, "is_mod") and ctx.author.is_mod):
                await ctx.send("❌ Only mods can add derpisms.")
                return
            if len(parts) < 3:
                await ctx.send("⚠️ Usage: !derpism add <text>")
                return
            new_derpism = parts[2].strip()
            if not new_derpism:
                await ctx.send("⚠️ Cannot add empty derpism.")
                return
            await self.add_derpism(ctx, new_derpism)

        elif parts[1].isdigit():
            index = int(parts[1]) - 1  # 1-based input
            await self.send_derpism_by_index(ctx, index)
        else:
            await ctx.send("❌ Invalid usage. Try !derpism, !derpism 12, or !derpism add <text>")

    async def send_random_derpism(self, ctx):
        derpisms = self.load_derpisms()
        if not derpisms:
            await ctx.send("🫠 No derpisms found.")
            return
        quote = random.choice(derpisms)
        await ctx.send(f"🌀 Derpism: \"{quote}\"")

    async def send_derpism_by_index(self, ctx, index):
        derpisms = self.load_derpisms()
        if 0 <= index < len(derpisms):
            await ctx.send(f"📘 Derpism #{index + 1}: \"{derpisms[index]}\"")
        else:
            await ctx.send(f"❌ No derpism at #{index + 1}.")

    async def add_derpism(self, ctx, text):
        derpisms = self.load_derpisms()
        if text in derpisms:
            await ctx.send("⚠️ That derpism already exists.")
            return
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(f"{text}\n")
        await ctx.send(f"✅ Added derpism #{len(derpisms) + 1}: \"{text}\"")
        self.logger.info(f"Derpism added by {ctx.author.name}: {text}")

    def load_derpisms(self):
        if not os.path.isfile(self.file_path):
            return []
        with open(self.file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

def prepare(bot):
    print("prepare() called for DerpismCog; id(bot):", id(bot))  # DEBUG
    print(f"Current loaded cogs: {list(bot.cogs)}")  # Shows loaded cog names
    if not bot.get_cog("DerpismCog"):
        bot.add_cog(DerpismCog(bot))
        print("Loaded cog : DerpismCog")
    else:
        print("DerpismCog already loaded")