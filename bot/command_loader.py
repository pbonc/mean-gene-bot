import os
import random
import logging
from twitchio.ext import commands
from sfx_player import queue_sfx
import re
from datetime import datetime

SFX_FOLDER = "sfx"
VALID_COMMAND_RE = re.compile(r"^[a-zA-Z0-9]{1,32}$")
RANDOMIZER_REGISTRY = {}
ALLOWED_EXCEPTIONS = {"!", "$2"}  # Allow these even if they fail regex

def is_valid_command_name(name):
    return name in ALLOWED_EXCEPTIONS or VALID_COMMAND_RE.fullmatch(name)

def log_skip(reason, user, command, created=None):
    if command not in ALLOWED_EXCEPTIONS:
        msg = f"⛔ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {user} skipped: {reason} for !{command}"
        if created:
            msg += f" (account created: {created.date()})"
        print(msg)
        with open("logs/skipped-commands.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")

def load_sfx_commands(bot):
    print("🔍 Scanning for SFX commands...")
    command_names = set()
    registered_count = 0

    for root, _, files in os.walk(SFX_FOLDER):
        rel_path = os.path.relpath(root, SFX_FOLDER)
        if rel_path == ".":
            rel_path = ""

        mp3s = [f for f in files if f.lower().endswith(".mp3")]
        if not mp3s:
            continue

        for f in mp3s:
            name = os.path.splitext(f)[0]
            if rel_path:
                command_name = name
                full_path = os.path.join(SFX_FOLDER, rel_path, f)
            else:
                command_name = name
                full_path = os.path.join(SFX_FOLDER, f)

            if not is_valid_command_name(command_name):
                print(f"⚠️ Skipping invalid command name: !{command_name}")
                continue

            if command_name in command_names:
                continue  # Silently skip duplicates

            async def _cmd(ctx, path=full_path):
                await queue_sfx(path)

            try:
                bot.add_command(commands.Command(func=_cmd, name=command_name))
                command_names.add(command_name)
                registered_count += 1
            except commands.errors.CommandAlreadyExists:
                pass  # Silently skip already registered command
            except Exception as e:
                print(f"❌ Failed to register !{command_name}: {e}")

        if rel_path and rel_path not in RANDOMIZER_REGISTRY:
            mp3_paths = [os.path.join(root, f) for f in mp3s]
            random_name = rel_path.replace("\\", "/").split("/")[-1]
            if is_valid_command_name(random_name):
                def make_random_cmd(options):
                    async def _random_cmd(ctx):
                        choice = random.choice(options)
                        cmd = os.path.splitext(os.path.basename(choice))[0]
                        print(f"🎲 {ctx.author.name} triggered random sfx: !{cmd}")
                        await queue_sfx(choice)
                        await ctx.send(f"!{cmd}")
                    return _random_cmd

                bot.add_command(commands.Command(func=make_random_cmd(mp3_paths), name=random_name))
                RANDOMIZER_REGISTRY[random_name] = True
            else:
                print(f"⚠️ Invalid folder name for command: !{random_name}")

    async def _sfxcount(ctx):
        count = 0
        for _, _, files in os.walk(SFX_FOLDER):
            count += sum(1 for f in files if f.lower().endswith(".mp3"))
        await ctx.send(f"There are {count} SFX files available.")

    bot.add_command(commands.Command(func=_sfxcount, name="sfxcount"))
    print("✅ Fixed command registered: !sfxcount")
    print(f"✅ Total SFX commands registered: {registered_count}")
