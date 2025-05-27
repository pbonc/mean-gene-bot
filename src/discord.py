import os
import logging
import discord
from discord.ext import commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_MOD_CHANNEL_IDS = os.getenv("DISCORD_MOD_CHANNEL_IDS", "").split(",")

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")
    for guild in bot.guilds:
        logging.info(f"Connected to guild: {guild.name}")
        for channel in guild.text_channels:
            if str(channel.id) in DISCORD_MOD_CHANNEL_IDS:
                logging.info(f"Monitoring mod channel: {channel.name} ({channel.id})")

@bot.event
async def on_error(event, *args, **kwargs):
    logging.error(f"Discord error in {event}: {args} {kwargs}")

def run_discord_bot():
    logging.basicConfig(level=logging.INFO)
    bot.run(DISCORD_TOKEN)