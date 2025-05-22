import os
import random
from twitchio.ext import commands
from datetime import datetime

DAH_FIRST_PATH = os.path.join("bot", "data", "dah_first.txt")
DAH_SECOND_PATH = os.path.join("bot", "data", "dah_second.txt")

last_dah_use = None
cooldown_seconds = 5

class DarsAgainstHumanity(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="dah")
    async def dah(self, ctx):
        global last_dah_use
        now = datetime.utcnow()

        if last_dah_use and (now - last_dah_use).total_seconds() < cooldown_seconds:
            remaining = int(cooldown_seconds - (now - last_dah_use).total_seconds())
            print(f"⏱️ !dah is on cooldown — try again in {remaining} seconds")
            return

        if not os.path.exists(DAH_FIRST_PATH) or not os.path.exists(DAH_SECOND_PATH):
            print("❌ Missing DAH data files.")
            return

        with open(DAH_FIRST_PATH, "r", encoding="utf-8") as f:
            first_lines = [line.strip() for line in f if "::" in line]

        with open(DAH_SECOND_PATH, "r", encoding="utf-8") as f:
            second_lines = [line.strip() for line in f if line.strip()]

        if not first_lines or not second_lines:
            print("⚠️ No DAH lines available.")
            return

        setup_entry = random.choice(first_lines)
        try:
            count_str, setup_text = setup_entry.split("::", 1)
            punch_count = int(count_str.strip())
        except ValueError:
            print(f"⚠️ Malformed setup entry: {setup_entry}")
            return

        if punch_count > len(second_lines):
            print(f"⚠️ Not enough punchlines available for {punch_count} requested.")
            return

        selected_punches = random.sample(second_lines, punch_count)

        output = setup_text
        for punch in selected_punches:
            if "______" in output:
                output = output.replace("______", punch, 1)
            else:
                output += f" {punch}"

        await ctx.send(output)
        last_dah_use = now

    @commands.command(name="dahfirst")
    async def dahfirst(self, ctx):
        if not ctx.author.is_mod:
            return

        parts = ctx.message.content.split(" ", 2)
        if len(parts) < 3 or not parts[1].isdigit():
            await ctx.send("⚠️ Usage: !dahfirst <count> <text with blanks>")
            return

        count = int(parts[1])
        text = parts[2].strip()
        line_to_add = f"{count}::{text}"

        with open(DAH_FIRST_PATH, "a", encoding="utf-8") as f:
            f.write(line_to_add + "\n")

        await ctx.send(f"✅ Added setup requiring {count} punchline(s): '{text}'")

    @commands.command(name="dahsecond")
    async def dahsecond(self, ctx):
        if not ctx.author.is_mod:
            return

        parts = ctx.message.content.split(" ", 1)
        if len(parts) != 2:
            await ctx.send("⚠️ Usage: !dahsecond <punchline text>")
            return

        text = parts[1].strip()

        with open(DAH_SECOND_PATH, "a", encoding="utf-8") as f:
            f.write(text + "\n")

        await ctx.send(f"✅ Added punchline: '{text}'")


def prepare(bot: commands.Bot):
    if bot.get_cog("DarsAgainstHumanity"):
        print("⚠️ DarsAgainstHumanity already loaded, skipping.")
        return
    bot.add_cog(DarsAgainstHumanity(bot))
