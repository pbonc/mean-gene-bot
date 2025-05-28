print("=== STARTING Mean Gene Bot ===")

import os
import logging
from twitchio.ext import commands
import asyncio
from dotenv import load_dotenv

print("Loaded basic imports.")

# --- Import cog loaders and SFX registry builder ---
try:
    from twitch_commands import load_all_cogs
    print("Imported load_all_cogs from twitch_commands.")
except Exception as e:
    print("FAILED to import load_all_cogs:", e)

try:
    from sfx_watcher import build_sfx_registry, SFXRegistry
    print("Imported build_sfx_registry from sfx_watcher.")
except Exception as e:
    print("FAILED to import build_sfx_registry:", e)

try:
    from sfx import prepare as prepare_sfx
    print("Imported prepare_sfx from sfx.")
except Exception as e:
    print("FAILED to import prepare_sfx:", e)

try:
    from command_router import prepare as prepare_command_router
    print("Imported prepare_command_router from command_router.")
except Exception as e:
    print("FAILED to import prepare_command_router:", e)

# --- Logging setup ---
os.makedirs("logs", exist_ok=True)
print("Ensured logs directory exists.")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot_debug.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)
print("Logging configured.")

# --- Environment loading ---
print("Loading .env...")
load_dotenv()
print(".env loaded.")

TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_CHANNELS_RAW = os.getenv("TWITCH_CHANNELS", "yourchannel,iamdar")

print(f"TWITCH_TOKEN: {TWITCH_TOKEN}")
print(f"TWITCH_CLIENT_ID: {TWITCH_CLIENT_ID}")
print(f"TWITCH_CLIENT_SECRET: {TWITCH_CLIENT_SECRET}")
print(f"TWITCH_CHANNELS_RAW: {TWITCH_CHANNELS_RAW}")

if not TWITCH_TOKEN: raise RuntimeError("TWITCH_TOKEN is not set! Check your .env file.")
if not TWITCH_CLIENT_ID: raise RuntimeError("TWITCH_CLIENT_ID is not set! Check your .env file.")
if not TWITCH_CLIENT_SECRET: raise RuntimeError("TWITCH_CLIENT_SECRET is not set! Check your .env file.")
if not TWITCH_CHANNELS_RAW: raise RuntimeError("TWITCH_CHANNELS is not set! Check your .env file.")

TWITCH_CHANNELS = [ch.strip() for ch in TWITCH_CHANNELS_RAW.split(",") if ch.strip()]
print(f"TWITCH_CHANNELS parsed: {TWITCH_CHANNELS}")

def run_twitch_bot():
    print("Entering run_twitch_bot()")
    logger.info("Starting Twitch bot event loop.")
    asyncio.set_event_loop(asyncio.new_event_loop())
    print("Created new asyncio event loop.")

    # --- Build SFX registry BEFORE loading cogs ---
    sfx_registry = None
    if 'build_sfx_registry' in globals() and build_sfx_registry:
        try:
            sfx_registry = build_sfx_registry()
            if hasattr(sfx_registry, 'sfx_dir'):
                print(f"SFX base directory: {sfx_registry.sfx_dir}")
            print(f"SFX registry built: {sfx_registry}")
            if hasattr(sfx_registry, 'file_commands'):
                print(f"SFX file commands: {len(sfx_registry.file_commands)}")
            if hasattr(sfx_registry, 'folder_commands'):
                print(f"SFX folder commands: {len(sfx_registry.folder_commands)}")
        except Exception as e:
            print(f"Failed to build SFX registry: {e}")
    else:
        print("No build_sfx_registry available, skipping SFX registry.")

    # --- Instantiate bot ---
    bot = commands.Bot(
        token=TWITCH_TOKEN,
        prefix="!",
        initial_channels=TWITCH_CHANNELS
    )
    print("Bot instantiated.")
    bot.sfx_registry = sfx_registry  # Make registry available to cogs
    if sfx_registry and hasattr(sfx_registry, 'sfx_dir'):
        bot.sfx_dir = sfx_registry.sfx_dir
    print(f"Assigned sfx_registry to bot: {bot.sfx_registry}")
    if hasattr(bot, "sfx_dir"):
        print(f"Assigned sfx_dir to bot: {bot.sfx_dir}")

    # --- Load all regular cogs ---
    print("About to load all cogs...")
    if 'load_all_cogs' in globals() and load_all_cogs:
        load_all_cogs(bot)
    print("All cogs loaded.")

    # --- Load SFXCog explicitly after all other cogs ---
    if 'prepare_sfx' in globals() and prepare_sfx:
        prepare_sfx(bot)
        print("SFXCog loaded.")

    # --- Load CommandRouter last so it can intercept messages and call handle_commands only for non-SFX commands ---
    if 'prepare_command_router' in globals() and prepare_command_router:
        prepare_command_router(bot)
        print("CommandRouter cog loaded.")

    print("About to run bot...")
    bot.run()
    print("bot.run() returned (should never get here unless bot stops).")

if __name__ == "__main__":
    print("Running as __main__!")
    run_twitch_bot()
    print("End of main.py reached (should never see this unless bot.run() exits).")