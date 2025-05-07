import os
from dotenv import load_dotenv

load_dotenv()

TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
BOT_NICK = os.getenv("BOT_NICK", "meangenebot")
CHANNEL = os.getenv("CHANNEL", "iamdar")