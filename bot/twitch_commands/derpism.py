import os
import random
from twitchio.ext import commands

DERPISM_FILE = "bot/data/derpisms.txt"

class Derpism(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = DERPISM_FILE
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.isfile(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write("")

    @commands.command(name="derpism")
    async def derpism_command(self, ctx: commands.Context):
        parts = ctx.message.content.split(maxsplit=2)

        if len(parts) == 1:
            # !derpism
            await self.send_random_derpism(ctx)

        elif parts[1].lower() == "add" and ctx.author.is_mod:
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

    def load_derpisms(self):
        if not os.path.isfile(self.file_path):
            return []
        with open(self.file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

def prepare(bot: commands.Bot):
    bot.add_cog(Derpism(bot))
