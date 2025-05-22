import os
import random
from twitchio.ext import commands

TIC_FILE = "bot/data/tic.txt"

class TankInCollege(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = TIC_FILE
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.isfile(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write("")

    @commands.command(name="tic")
    async def tic_command(self, ctx: commands.Context):
        parts = ctx.message.content.split(maxsplit=2)

        if len(parts) == 1:
            # !tic
            await self.send_random_tic(ctx)

        elif parts[1].lower() == "add" and ctx.author.is_mod:
            if len(parts) < 3:
                await ctx.send("⚠️ Usage: !tic add <text>")
                return
            new_entry = parts[2].strip()
            if not new_entry:
                await ctx.send("⚠️ Cannot add empty entry.")
                return
            await self.add_tic(ctx, new_entry)

        elif parts[1].isdigit():
            index = int(parts[1]) - 1  # 1-based input
            await self.send_tic_by_index(ctx, index)

        else:
            await ctx.send("❌ Invalid usage. Try !tic, !tic 12, or !tic add <text>")

    async def send_random_tic(self, ctx):
        entries = self.load_tics()
        if not entries:
            await ctx.send("🫠 No TIC entries found.")
            return
        quote = random.choice(entries)
        await ctx.send(f"🎓 TIC: \"{quote}\"")

    async def send_tic_by_index(self, ctx, index):
        entries = self.load_tics()
        if 0 <= index < len(entries):
            await ctx.send(f"📘 TIC #{index + 1}: \"{entries[index]}\"")
        else:
            await ctx.send(f"❌ No TIC entry at #{index + 1}.")

    async def add_tic(self, ctx, text):
        entries = self.load_tics()
        if text in entries:
            await ctx.send("⚠️ That entry already exists.")
            return
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(f"{text}\n")
        await ctx.send(f"✅ Added TIC #{len(entries) + 1}: \"{text}\"")

    def load_tics(self):
        if not os.path.isfile(self.file_path):
            return []
        with open(self.file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

def prepare(bot: commands.Bot):
    bot.add_cog(TankInCollege(bot))
