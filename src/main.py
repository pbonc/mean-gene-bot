import threading
import time
from twitch_bot import run_twitch_bot
from discord_bot import run_discord_bot

def main():
    print("Welcome to the main event!")

    # Start Twitch bot in a thread
    twitch_thread = threading.Thread(target=run_twitch_bot, name="TwitchBotThread", daemon=True)
    twitch_thread.start()
    print("Connecting to Twitch...")

    # Start Discord bot in a thread
    discord_thread = threading.Thread(target=run_discord_bot, name="DiscordBotThread", daemon=True)
    discord_thread.start()
    print("Connecting to Discord...")

    # Keep main thread alive while bots run
    try:
        while True:
            time.sleep(1)
            # Optionally, you could add health checks/logs here
    except KeyboardInterrupt:
        print("\nShutting down bots...")

if __name__ == "__main__":
    main()