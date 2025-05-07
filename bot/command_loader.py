# bot/command_loader.py

import os
import random
from twitchio.ext import commands
from sfx_player import queue_sfx



SFX_ROOT = os.path.join(os.path.dirname(__file__), "sfx")


def load_sfx_commands(bot: commands.Bot):
    for root, _, files in os.walk(SFX_ROOT):
        rel_path = os.path.relpath(root, SFX_ROOT)

        for filename in files:
            if not filename.lower().endswith(".mp3"):
                continue

            name_no_ext = os.path.splitext(filename)[0].lower()
            file_path = os.path.join(root, filename)

            # Closure-safe command creator
            def make_specific_player(path, cmd_name):
                async def _cmd(ctx):
                    from .sfx_player import queue_sfx  # ✅ Relative import
                    await queue_sfx(path)
                    await ctx.send(f"{ctx.author.name} triggered !{cmd_name}")
                return _cmd

            cmd_func = make_specific_player(file_path, name_no_ext)
            bot.add_command(commands.Command(name=name_no_ext, func=cmd_func))

        # If it's a subfolder, add a random-play command
        if rel_path != ".":
            folder_command = os.path.basename(rel_path).lower()
            file_paths = [
                os.path.join(root, f) for f in files if f.lower().endswith(".mp3")
            ]

            def make_random_player(paths, folder_name):
                async def _cmd(ctx):
                    from .sfx_player import queue_sfx  # ✅ Relative import
                    chosen = random.choice(paths)
                    await queue_sfx(chosen)
                    await ctx.send(f"{ctx.author.name} triggered !{folder_name}")
                return _cmd

            cmd_func = make_random_player(file_paths, folder_command)
            bot.add_command(commands.Command(name=folder_command, func=cmd_func))
