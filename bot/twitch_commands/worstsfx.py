import os
import random
import glob
from twitchio.ext import commands
from bot.sfx_player import queue_sfx, get_worst_sfx

SFX_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sfx"))

def register_worstsfx(bot):
    async def _worstsfx(ctx):
        worst_path = get_worst_sfx(SFX_FOLDER)
        if not worst_path:
            await ctx.send("No SFX files found!")
            return

        cmd = os.path.splitext(os.path.basename(worst_path))[0]
        print(f"🐢 {ctx.author.name} triggered !worstsfx → !{cmd}")
        await queue_sfx(worst_path)
        await ctx.send(f"!{cmd}")

    try:
        bot.add_command(commands.Command(func=_worstsfx, name="worstsfx"))
        print("✅ Registered Twitch command: !worstsfx")
    except Exception as e:
        print(f"❌ Failed to register !worstsfx: {e}")
