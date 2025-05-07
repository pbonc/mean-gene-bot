import os
import random
from twitchio.ext import commands
from sfx_player import queue_sfx

SFX_ROOT = os.path.join(os.path.dirname(__file__), "sfx")
loaded_commands = set()

# Prevent collision with manual or special commands
RESERVED_COMMANDS = {"sfxcount"}


def load_sfx_commands(bot: commands.Bot):
    for root, _, files in os.walk(SFX_ROOT):
        rel_path = os.path.relpath(root, SFX_ROOT)

        for filename in files:
            if not filename.lower().endswith(".mp3"):
                continue

            name_no_ext = os.path.splitext(filename)[0].lower()
            if name_no_ext in RESERVED_COMMANDS:
                continue

            file_path = os.path.join(root, filename)

            def make_specific_player(path):
                async def _cmd(ctx):
                    await queue_sfx(path)
                return _cmd

            if name_no_ext not in loaded_commands:
                cmd_func = make_specific_player(file_path)
                bot.add_command(commands.Command(name=name_no_ext, func=cmd_func))
                loaded_commands.add(name_no_ext)

        if rel_path != ".":
            folder_command = os.path.basename(rel_path).lower()
            if folder_command in RESERVED_COMMANDS:
                continue

            file_paths = [
                os.path.join(root, f) for f in files if f.lower().endswith(".mp3")
            ]

            def make_random_player(paths):
                async def _cmd(ctx):
                    chosen = random.choice(paths)
                    await queue_sfx(chosen)
                return _cmd

            if folder_command not in loaded_commands:
                cmd_func = make_random_player(file_paths)
                bot.add_command(commands.Command(name=folder_command, func=cmd_func))
                loaded_commands.add(folder_command)

    if "sfxcount" not in loaded_commands:
        async def sfx_count_command(ctx):
            count = sum(
                1 for root, _, files in os.walk(SFX_ROOT)
                for f in files if f.lower().endswith(".mp3")
            )
            await ctx.send(f"There are {count} sound effects loaded.")

        bot.add_command(commands.Command(name="sfxcount", func=sfx_count_command))
        loaded_commands.add("sfxcount")

        # 🎲 !randomsfx command
    if "randomsfx" not in loaded_commands:
        async def randomsfx_command(ctx):
            all_mp3s = [
                os.path.join(root, f)
                for root, _, files in os.walk(SFX_ROOT)
                for f in files if f.lower().endswith(".mp3")
            ]
            if all_mp3s:
                chosen = random.choice(all_mp3s)
                await queue_sfx(chosen)

        bot.add_command(commands.Command(name="randomsfx", func=randomsfx_command))
        loaded_commands.add("randomsfx")
