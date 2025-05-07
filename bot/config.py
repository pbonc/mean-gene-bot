import os

# Twitch authentication and bot identity
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")  # Example: 'oauth:abcd1234...'
BOT_NICK = os.getenv("BOT_NICK", "meangenebot")  # Current bot username
CHANNEL = os.getenv("CHANNEL", "iamdar")   # The Twitch channel to join
