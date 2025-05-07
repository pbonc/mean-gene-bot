import os

TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")  # Should start with "oauth:"
BOT_NICK = os.getenv("BOT_NICK", "meangenebot")  # Updated default
CHANNEL = os.getenv("CHANNEL", "iamdar")