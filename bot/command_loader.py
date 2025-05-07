# bot/command_loader.py

import os
import random
from twitchio.ext import commands

SFX_ROOT = os.path.join(os.path.dirname(__file__), "sfx")


def load_sfx_commands(bot: commands.Bot):
    for root, _, files in os.walk(SFX_ROOT):
        rel_path = os.path.relpath(root, SFX_ROOT)

        for filename in files:
            if not filename.lower().endswith(".mp3"):
                continue

            name_no_ext = os.path.splitext(filename)[0]

            # !d, !lenny1, !lenny2, etc.
            command_name = name_no_ext.lower()

            file_path = os.path.join(root, filename)

            async def specific_player(ctx, path=file_path):
                from sfx_player import queue_sfx
                await queue_sfx(path)
                await ctx.send(f"{ctx.author.name} triggered !{command_name}")

            bot.add_command(commands.Command(specific_player, name=command_name))

        # If we're in a subfolder, create a folder-level randomizer command
        if rel_path != ".":
            folder_command = os.path.basename(rel_path).lower()
            file_paths = [
                os.path.join(root, f) for f in files if f.lower().endswith(".mp3")
            ]

            async def random_player(ctx, paths=file_paths):
                chosen = random.choice(paths)
                from sfx_player import queue_sfx
                await queue_sfx(chosen)
                await ctx.send(f"{ctx.author.name} triggered !{folder_command}")

            bot.add_command(commands.Command(random_player, name=folder_command))
