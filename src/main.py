print("=== STARTING Mean Gene Bot ===")

# --- Purge .pyc files and __pycache__ folders FIRST ---
import os
import shutil

def purge_pyc_and_pycache(start_dir):
    removed = 0
    for root, dirs, files in os.walk(start_dir):
        for file in files:
            if file.endswith('.pyc'):
                try:
                    os.remove(os.path.join(root, file))
                    removed += 1
                except Exception:
                    pass
        # Remove __pycache__ dirs after files
        for dir in dirs:
            if dir == '__pycache__':
                full = os.path.join(root, dir)
                try:
                    shutil.rmtree(full)
                except Exception:
                    pass
    print(f"Purged {removed} .pyc files and all __pycache__ dirs from {start_dir}")

purge_pyc_and_pycache(os.path.dirname(__file__))

import logging
from twitchio.ext import commands
import asyncio
from dotenv import load_dotenv
import threading

# --- Import SFX registry and SFXCog loader (FIXED imports) ---
try:
    from sfx_registry import build_sfx_registry, SFXRegistry
    print("Imported build_sfx_registry from sfx_registry.")
except Exception as e:
    print("FAILED to import build_sfx_registry:", e)

try:
    from twitch_commands.sfx import prepare as prepare_sfx
    print("Imported prepare_sfx from twitch_commands.sfx.")
except Exception as e:
    print("FAILED to import prepare_sfx:", e)

# --- Import cog loaders ---
try:
    from twitch_commands import load_all_cogs
    print("Imported load_all_cogs from twitch_commands.")
except Exception as e:
    print("FAILED to import load_all_cogs:", e)

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

# === Overlay Server Integration ===
def start_overlay_ws_server():
    # Import here to avoid import errors if overlay backend is missing
    from backend.ws_server import start_ws_server_threaded
    ws_thread = threading.Thread(target=start_ws_server_threaded, daemon=True)
    ws_thread.start()
    print("Overlay WebSocket server thread started.")

def start_overlay_http_server():
    # Serve overlay.html and gifs via HTTP for OBS
    import http.server
    import socketserver
    overlay_dir = os.path.join(os.path.dirname(__file__), 'overlay')
    os.chdir(overlay_dir)
    Handler = http.server.SimpleHTTPRequestHandler
    httpd = socketserver.TCPServer(("", 8081), Handler)
    print("Overlay HTTP server serving at http://localhost:8081")
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()
    return httpd

def run_twitch_bot():
    print("Entering run_twitch_bot()")
    logger.info("Starting Twitch bot event loop.")
    asyncio.set_event_loop(asyncio.new_event_loop())
    print("Created new asyncio event loop.")

    # --- Build SFX registry BEFORE loading cogs ---
    sfx_registry = None
    try:
        sfx_registry = build_sfx_registry()
        if hasattr(sfx_registry, 'sfx_root'):
            print(f"SFX base directory: {sfx_registry.sfx_root}")
        print(f"SFX registry built: {sfx_registry}")
        if hasattr(sfx_registry, 'file_commands'):
            print(f"SFX file commands: {len(sfx_registry.file_commands)}")
            print(f"SFX file command map: {sfx_registry.file_commands}")
        if hasattr(sfx_registry, 'folder_commands'):
            print(f"SFX folder commands: {len(sfx_registry.folder_commands)}")
    except Exception as e:
        print(f"Failed to build SFX registry: {e}")

    # --- Instantiate bot ---
    bot = commands.Bot(
        token=TWITCH_TOKEN,
        prefix="!",
        initial_channels=TWITCH_CHANNELS
    )
    print("Bot instantiated.")
    bot.sfx_registry = sfx_registry  # Make registry available to cogs
    if sfx_registry and hasattr(sfx_registry, 'sfx_root'):
        bot.sfx_dir = sfx_registry.sfx_root
    print(f"Assigned sfx_registry to bot: {bot.sfx_registry}")
    if hasattr(bot, "sfx_dir"):
        print(f"Assigned sfx_dir to bot: {bot.sfx_dir}")

    # --- Load all regular cogs ---
    print("About to load all cogs...")
    if 'load_all_cogs' in globals() and load_all_cogs:
        load_all_cogs(bot)
    print("All cogs loaded.")

    # --- SFXCog: Ensure it is loaded! ---
    if 'prepare_sfx' in globals() and prepare_sfx:
        prepare_sfx(bot)
        print("SFXCog loaded.")

    # --- CommandRouter: Only if not loaded by load_all_cogs ---
    if 'prepare_command_router' in globals() and prepare_command_router:
        prepare_command_router(bot)
        print("CommandRouter cog loaded.")

    print("About to run bot...")
    bot.run()
    print("bot.run() returned (should never get here unless bot stops).")

if __name__ == "__main__":
    print("Running as __main__!")
    # === Start Overlay Servers before bot ===
    start_overlay_ws_server()
    start_overlay_http_server()  # Optional: comment out if you serve with nginx or another HTTP server
    run_twitch_bot()
    print("End of main.py reached (should never see this unless bot.run() exits).")