import os
import importlib
from bot.twitch_commands.worstsfx import register_worstsfx
from bot.data.command_loader import load_sfx_commands

def load_all(bot, sfx_debug=False):
    print("📦 Loading SFX commands...")
    load_sfx_commands(bot, verbose=sfx_debug)

    print("📦 Loading utility commands...")
    register_worstsfx(bot)

    print("🧠 Loading Twitch command modules...")
    twitch_cmd_dir = os.path.join(os.path.dirname(__file__), "twitch_commands")

    for file in os.listdir(twitch_cmd_dir):
        if file.endswith(".py") and not file.startswith("__") and file != "worstsfx.py":
            module_name = f"bot.twitch_commands.{file[:-3]}"
            try:
                mod = importlib.import_module(module_name)
                if hasattr(mod, "prepare"):
                    mod.prepare(bot)
                    print(f"✅ Loaded: {module_name}")
                else:
                    print(f"⚠️ Skipped (no prepare()): {module_name}")
            except Exception as e:
                print(f"❌ Error loading {module_name}: {e}")
