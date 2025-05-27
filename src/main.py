import os
import threading
import time
from twitch_bot import run_twitch_bot
from discord_bot import run_discord_bot
from dotenv import load_dotenv

def main():
    print("Welcome to the main event!")
    load_dotenv()  # Ensure .env is loaded for both bots

    # Load tokens for validation
    TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

    # Start Twitch bot if token exists
    twitch_thread = None
    if TWITCH_TOKEN:
        twitch_thread = threading.Thread(target=run_twitch_bot, name="TwitchBotThread", daemon=True)
        twitch_thread.start()
        print("Connecting to Twitch...")
    else:
        print("TWITCH_TOKEN not found in environment. Skipping Twitch bot.")

    # Start Discord bot if token exists
    discord_thread = None
    if DISCORD_TOKEN:
        discord_thread = threading.Thread(target=run_discord_bot, name="DiscordBotThread", daemon=True)
        discord_thread.start()
        print("Connecting to Discord...")
    else:
        print("DISCORD_TOKEN not found in environment. Skipping Discord bot.")

    # Keep main thread alive while at least one bot is running
    try:
        while (twitch_thread and twitch_thread.is_alive()) or (discord_thread and discord_thread.is_alive()):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down bots...")

if __name__ == "__main__":
    main()