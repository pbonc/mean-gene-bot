import os
import random
import logging
from twitchio.ext import commands
from twitchio.ext.commands.errors import TwitchCommandError
from bot.sfx_player import queue_sfx
import re
from datetime import datetime
import glob

SFX_FOLDER = os.path.join(os.path.dirname(__file__), "sfx")
VALID_COMMAND_RE = re.compile(r"^[a-zA-Z0-9]{1,32}$")
RANDOMIZER_REGISTRY = {}
ALLOWED_EXCEPTIONS = {"!", "$2", "!!"}

def is_valid_command_name(name):
    name = name.lower()
    return name in ALLOWED_EXCEPTIONS or VALID_COMMAND_RE.fullmatch(name)

def log_skip(reason, user, command, created=None):
    if command.lower() not in ALLOWED_EXCEPTIONS:
        msg = f"⛔ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {user} skipped: {reason} for !{command}"
        if created:
            msg += f" (account created: {created.date()})"
        print(msg)
        with open("logs/skipped-commands.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")

def load_sfx_commands(bot, verbose=False):
    if verbose:
        print("🔍 Scanning for SFX commands...")

    command_names = set()
    registered_count = 0
    new_commands = []

    def make_cmd(path):
        async def _cmd(ctx):
            await queue_sfx(path)
        return _cmd

    for root, _, files in os.walk(SFX_FOLDER):
        rel_path = os.path.relpath(root, SFX_FOLDER)
        if rel_path == ".":
            rel_path = ""

        mp3s = [f for f in files if f.lower().endswith(".mp3")]
        if not mp3s:
            continue

        for f in mp3s:
            name = os.path.splitext(f)[0]
            command_name = name.lower()
            full_path = os.path.join(SFX_FOLDER, rel_path, f) if rel_path else os.path.join(SFX_FOLDER, f)

            if not is_valid_command_name(command_name):
                if verbose:
                    print(f"⚠️ Skipping invalid command name: !{command_name}")
                continue

            if command_name in command_names:
                continue

            try:
                bot.add_command(commands.Command(func=make_cmd(full_path), name=command_name))
                command_names.add(command_name)
                registered_count += 1
                if verbose:
                    print(f"✅ Registered new SFX command: !{command_name}")
                new_commands.append(command_name)
            except TwitchCommandError as e:
                if "already exists" in str(e):
                    pass
                else:
                    print(f"❌ TwitchCommandError for !{command_name}: {e}")
            except Exception as e:
                print(f"❌ Failed to register !{command_name}: {e}")

        if rel_path and rel_path not in RANDOMIZER_REGISTRY:
            mp3_paths = [os.path.join(root, f) for f in mp3s]
            random_name = rel_path.replace("\\", "/").split("/")[-1].lower()
            if is_valid_command_name(random_name):
                def make_random_cmd(options):
                    async def _random_cmd(ctx):
                        choice = random.choice(options)
                        cmd = os.path.splitext(os.path.basename(choice))[0]
                        print(f"🎲 {ctx.author.name} triggered random sfx: !{cmd}")
                        await queue_sfx(choice)
                        await ctx.send(f"!{cmd}")
                    return _random_cmd

                try:
                    bot.add_command(commands.Command(func=make_random_cmd(mp3_paths), name=random_name))
                    RANDOMIZER_REGISTRY[random_name] = True
                    if verbose:
                        print(f"📂 Registered folder randomizer: !{random_name} ({len(mp3_paths)} files)")
                except TwitchCommandError as e:
                    if "already exists" in str(e):
                        pass
                    else:
                        print(f"❌ TwitchCommandError for !{random_name}: {e}")
                except Exception as e:
                    print(f"❌ Failed to register folder randomizer !{random_name}: {e}")
            else:
                print(f"⚠️ Invalid folder name for command: !{random_name}")

    async def _sfxcount(ctx):
        count = 0
        for _, _, files in os.walk(SFX_FOLDER):
            count += sum(1 for f in files if f.lower().endswith(".mp3"))
        await ctx.send(f"There are {count} SFX files available.")

    try:
        bot.add_command(commands.Command(func=_sfxcount, name="sfxcount"))
        if verbose:
            print("✅ Fixed command registered: !sfxcount")
    except TwitchCommandError as e:
        if "already exists" in str(e):
            pass
        else:
            print(f"❌ TwitchCommandError: {e}")

    async def _random(ctx):
        all_mp3s = glob.glob(os.path.join(SFX_FOLDER, "**", "*.mp3"), recursive=True)
        if not all_mp3s:
            await ctx.send("No SFX files found!")
            return
        choice = random.choice(all_mp3s)
        cmd = os.path.splitext(os.path.basename(choice))[0]
        print(f"🎲 {ctx.author.name} triggered global random sfx: !{cmd}")
        await queue_sfx(choice)
        await ctx.send(f"!{cmd}")

    try:
        bot.add_command(commands.Command(func=_random, name="random"))
        if verbose:
            print("✅ Registered global randomizer command: !random")
    except TwitchCommandError as e:
        print(f"❌ Failed to register !random: {e}")

    if verbose:
        print(f"✅ Total SFX commands registered: {registered_count}")

    return new_commands
