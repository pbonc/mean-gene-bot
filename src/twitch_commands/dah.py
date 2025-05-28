import os
import random
from twitchio.ext import commands

DAH_FIRST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dah_first.txt")
DAH_SECOND_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dah_second.txt")

class DarsAgainstHumanity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="dah")
    async def dah(self, ctx):
        # Check if files exist
        if not os.path.exists(DAH_FIRST_PATH) or not os.path.exists(DAH_SECOND_PATH):
            await ctx.send("❌ DAH setup or punchline data files are missing.")
            return

        # Load setups and punchlines
        with open(DAH_FIRST_PATH, "r", encoding="utf-8") as f:
            first_lines = [line.strip() for line in f if "::" in line]

        with open(DAH_SECOND_PATH, "r", encoding="utf-8") as f:
            second_lines = [line.strip() for line in f if line.strip()]

        if not first_lines or not second_lines:
            await ctx.send("⚠️ No DAH lines available.")
            return

        # Pick a random setup
        setup_entry = random.choice(first_lines)
        try:
            count_str, setup_text = setup_entry.split("::", 1)
            punch_count = int(count_str.strip())
        except ValueError:
            await ctx.send("⚠️ Malformed setup entry.")
            return

        # Enforce that the setup text has the right count of blanks
        blank_count = setup_text.count("______")
        if punch_count != blank_count:
            await ctx.send("⚠️ Malformed setup: blank count mismatch. Skipping.")
            return

        if punch_count > len(second_lines):
            await ctx.send("⚠️ Not enough punchlines available for this setup.")
            return

        selected_punches = random.sample(second_lines, punch_count)
        output = setup_text
        for punch in selected_punches:
            if "______" in output:
                output = output.replace("______", punch, 1)
            else:
                output += f" {punch}"

        await ctx.send(output)

    @commands.command(name="dahfirst")
    async def dahfirst(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can add DAH setups.")
            return

        parts = ctx.message.content.split(" ", 2)
        if len(parts) < 3 or not parts[1].isdigit():
            await ctx.send("⚠️ Usage: !dahfirst <count> <text with blanks>")
            return

        count = int(parts[1])
        text = parts[2].strip()
        blank_count = text.count("______")

        if count != blank_count:
            await ctx.send(f"⚠️ The count ({count}) does not match the number of blanks ({blank_count}). Use six underscores per blank.")
            return

        line_to_add = f"{count}::{text}"
        with open(DAH_FIRST_PATH, "a", encoding="utf-8") as f:
            f.write(line_to_add + "\n")

        await ctx.send(f"✅ Added setup requiring {count} punchline(s): '{text}'")

    @commands.command(name="dahsecond")
    async def dahsecond(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can add DAH punchlines.")
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
        return
    bot.add_cog(DarsAgainstHumanity(bot))