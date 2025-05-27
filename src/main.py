import os
import threading
import time
from sfx_watcher import SFXWatcher
from twitch_bot import run_twitch_bot
from dotenv import load_dotenv

# --- Clean out log files at the start of each session ---
log_files = [
    "logs/sfx_creation.log",
    "logs/bot_debug.log"
]
for log_path in log_files:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8"):
        pass

def main():
    load_dotenv()  # Load environment variables from .env

    # Start SFX watcher (in a thread so it can watch for file changes)
    sfx_watcher = SFXWatcher()
    sfx_thread = threading.Thread(target=sfx_watcher.start, name="SFXWatcher", daemon=True)
    sfx_thread.start()

    # Give watcher a little time to populate registry before starting the bot
    time.sleep(1)

    # Start Twitch bot (pass in SFX registry for dynamic SFX commands)
    twitch_thread = threading.Thread(
        target=run_twitch_bot,
        kwargs={'sfx_registry': sfx_watcher.registry},
        name="TwitchBotThread",
        daemon=True
    )
    twitch_thread.start()

    # Optionally: Add Discord bot startup here if desired

    # Keep main thread alive while watcher or bot is running
    try:
        while (sfx_thread and sfx_thread.is_alive()) or (twitch_thread and twitch_thread.is_alive()):
            time.sleep(1)
    except KeyboardInterrupt:
        sfx_watcher.stop()

if __name__ == "__main__":
    main()