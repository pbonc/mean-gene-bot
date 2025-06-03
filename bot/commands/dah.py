import os
import random
import logging
from twitchio.ext import commands
from .base_command import mod_only

# Paths for DAH files in assets/txt/
DAH_FIRST_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "txt", "dah_first.txt")
)
DAH_SECOND_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "txt", "dah_second.txt")
)

def load_setups():
    if not os.path.isfile(DAH_FIRST_PATH):
        return []
    with open(DAH_FIRST_PATH, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if "::" in line]

def load_punchlines():
    if not os.path.isfile(DAH_SECOND_PATH):
        return []
    with open(DAH_SECOND_PATH, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

class DarsAgainstHumanity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("dah")

    @commands.command(name="dah")
    async def dah(self, ctx):
        setups = load_setups()
        punches = load_punchlines()
        if not setups or not punches:
            await ctx.send("❌ DAH setup or punchline data files are missing or empty.")
            return

        setup_entry = random.choice(setups)
        try:
            count_str, setup_text = setup_entry.split("::", 1)
            punch_count = int(count_str.strip())
        except ValueError:
            await ctx.send("⚠️ Malformed setup entry.")
            return

        blank_count = setup_text.count("______")
        if punch_count != blank_count:
            await ctx.send("⚠️ Malformed setup: blank count mismatch. Skipping.")
            return

        if punch_count > len(punches):
            await ctx.send("⚠️ Not enough punchlines available for this setup.")
            return

        selected = random.sample(punches, punch_count)
        output = setup_text
        for punch in selected:
            if "______" in output:
                output = output.replace("______", punch, 1)
            else:
                output += f" {punch}"

        await ctx.send(output)

    @commands.command(name="dahfirst")
    @mod_only
    async def dahfirst(self, ctx):
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
        self.logger.info(f"DAH setup added by {ctx.author.name}: {line_to_add}")

    @commands.command(name="dahsecond")
    @mod_only
    async def dahsecond(self, ctx):
        punchline = ctx.message.content[len("!dahsecond"):].strip()
        if not punchline:
            await ctx.send("⚠️ Usage: !dahsecond <punchline text>")
            return

        with open(DAH_SECOND_PATH, "a", encoding="utf-8") as f:
            f.write(punchline + "\n")

        await ctx.send(f"✅ Added punchline: '{punchline}'")
        self.logger.info(f"DAH punchline added by {ctx.author.name}: {punchline}")

def prepare(bot):
    if not bot.get_cog("DarsAgainstHumanity"):
        bot.add_cog(DarsAgainstHumanity(bot))