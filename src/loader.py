import os
import random
import glob
import re
import importlib
from datetime import datetime
from twitchio.ext import commands
from twitchio.ext.commands.errors import TwitchCommandError
from bot.sfx_player import queue_sfx

print(f"🧠 USING COMMAND_LOADER FROM: {__file__}")

# -- Constants & Globals --
SFX_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sfx"))
TWITCH_COMMANDS_DIR = os.path.join(os.path.dirname(__file__), "twitch_commands")

print(f"🔍 SFX_FOLDER resolved to: {SFX_FOLDER}")

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
    if not os.path.exists(SFX_FOLDER):
        print(f"❌ SFX folder does not exist at path: {SFX_FOLDER}")
        return []

    command_names = set()
    new_commands = []

    def make_cmd(path):
        async def _cmd(ctx):
            if verbose:
                print(f"🎮 SFX command triggered for: {path}")
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
            full_path = os.path.join(root, f)

            if not is_valid_command_name(command_name) or command_name in command_names:
                continue

            try:
                bot.add_command(commands.Command(func=make_cmd(full_path), name=command_name))
                command_names.add(command_name)
                new_commands.append(command_name)
            except TwitchCommandError as e:
                if "already exists" not in str(e):
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
                        if verbose:
                            print(f"🎲 {ctx.author.name} triggered random sfx: !{cmd} (folder randomizer)")
                        await queue_sfx(choice)
                        await ctx.send(f"!{cmd}")
                    return _random_cmd

                try:
                    bot.add_command(commands.Command(func=make_random_cmd(mp3_paths), name=random_name))
                    RANDOMIZER_REGISTRY[random_name] = True
                except Exception as e:
                    print(f"❌ Failed to register folder randomizer !{random_name}: {e}")

    # Register !sfxcount
    async def _sfxcount(ctx):
        count = sum(
            1 for _, _, files in os.walk(SFX_FOLDER)
            for f in files if f.lower().endswith(".mp3")
        )
        await ctx.send(f"There are {count} SFX files available.")

    try:
        bot.add_command(commands.Command(func=_sfxcount, name="sfxcount"))
    except TwitchCommandError as e:
        if "already exists" not in str(e):
            print(f"❌ TwitchCommandError: {e}")

    # Register global !random
    async def _random(ctx):
        all_mp3s = glob.glob(os.path.join(SFX_FOLDER, "**", "*.mp3"), recursive=True)
        if not all_mp3s:
            await ctx.send("No SFX files found!")
            return
        choice = random.choice(all_mp3s)
        cmd = os.path.splitext(os.path.basename(choice))[0]
        if verbose:
            print(f"🎲 {ctx.author.name} triggered global random sfx: !{cmd}")
        await queue_sfx(choice)
        await ctx.send(f"!{cmd}")

    try:
        bot.add_command(commands.Command(func=_random, name="random"))
    except TwitchCommandError as e:
        if "already exists" not in str(e):
            print(f"❌ TwitchCommandError (random): {e}")

    return new_commands

def load_all(bot, sfx_debug=False):
    # Track loaded modules to avoid loading twice
    loaded = set()

    # Dynamically load all twitch_commands/*.py modules that expose prepare(bot)
    for filename in os.listdir(TWITCH_COMMANDS_DIR):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        mod_name = filename[:-3]  # Strip .py
        full_module = f"bot.twitch_commands.{mod_name}"

        # Prevent loading the same cog twice
        if full_module in loaded or full_module in getattr(bot, "extensions", {}):
            print(f"⚠️ {full_module} already loaded, skipping.")
            continue

        try:
            module = importlib.import_module(full_module)
            if hasattr(module, "prepare"):
                module.prepare(bot)
                print(f"✅ Loaded: {full_module}")
                loaded.add(full_module)
            else:
                print(f"⚠️ Skipped (no prepare()): {full_module}")
        except Exception as e:
            print(f"❌ Error loading {full_module}: {e}")

    # Load dynamic SFX commands, only once
    load_sfx_commands(bot, verbose=sfx_debug)

def register_sfx_command(bot, command_name: str):
    sfx_path = None

    for root, _, files in os.walk(SFX_FOLDER):
        for file in files:
            if file.lower().endswith(".mp3"):
                name = os.path.splitext(file)[0].lower()
                if name == command_name:
                    sfx_path = os.path.join(root, file)
                    break
        if sfx_path:
            break

    if not sfx_path:
        print(f"⚠️ SFX file not found for command: {command_name}")
        return

    async def _sfx_cmd(ctx):
        print(f"🎮 Triggered new SFX command: !{command_name}")
        await queue_sfx(sfx_path)

    try:
        bot.add_command(commands.Command(func=_sfx_cmd, name=command_name))
    except Exception as e:
        print(f"❌ Could not register dynamic sfx !{command_name}: {e}")

def unregister_sfx_command(bot, command_name: str):
    """
    Remove an SFX command from the bot dynamically.
    """
    try:
        bot.remove_command(command_name)
        print(f"❌ Unregistered SFX command: !{command_name}")
    except Exception as e:
        print(f"⚠️ Error unregistering SFX command !{command_name}: {e}")