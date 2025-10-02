import os
from twitchio.ext import commands
ASSETS_TXT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "txt"))
os.makedirs(ASSETS_TXT_DIR, exist_ok=True)
MODNEWS_FILE = os.path.join(ASSETS_TXT_DIR, "modnews.txt")

class ModNewsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="modnews")
    async def modnews(self, ctx):
        parts = ctx.message.content.split(" ", 2)
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use this command.")
            return
        if len(parts) < 2:
            await ctx.send("Usage: !modnews add <message> | !modnews clear mine | !modnews clear all")
            return
        subcmd = parts[1].lower()
        username = ctx.author.name
        if subcmd == "add" and len(parts) == 3:
            msg = parts[2].strip().strip('"')
            entry = f"{msg} -{username}"
            with open(MODNEWS_FILE, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
            await ctx.send(f"Added modnews: {entry}")
        elif subcmd == "clear" and len(parts) >= 3:
            target = parts[2].lower()
            if target == "mine":
                # Remove all messages from this user
                if os.path.isfile(MODNEWS_FILE):
                    with open(MODNEWS_FILE, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    with open(MODNEWS_FILE, "w", encoding="utf-8") as f:
                        for line in lines:
                            if f"-{username}" not in line:
                                f.write(line)
                await ctx.send(f"Cleared your modnews messages.")
            elif target == "all":
                if os.path.isfile(MODNEWS_FILE):
                    os.remove(MODNEWS_FILE)
                await ctx.send("Cleared all modnews messages.")
            else:
                await ctx.send("Usage: !modnews clear mine | !modnews clear all")
        else:
            await ctx.send("Usage: !modnews add <message> | !modnews clear mine | !modnews clear all")

def prepare(bot):
    if not bot.get_cog("ModNewsCog"):
        bot.add_cog(ModNewsCog(bot))
