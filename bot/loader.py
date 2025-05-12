from bot.twitch_commands.worstsfx import register_worstsfx
from bot.data.command_loader import load_sfx_commands

def load_all(bot, sfx_debug=False):
    print("📦 Loading SFX commands...")
    load_sfx_commands(bot, verbose=sfx_debug)

    print("📦 Loading utility commands...")
    register_worstsfx(bot)

    print("🧠 Registering internal cogs...")
