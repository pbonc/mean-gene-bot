from twitchio.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

bot = commands.Bot(
    token=os.getenv("TWITCH_TOKEN"),
    prefix="!",
    initial_channels=[os.getenv("CHANNEL")]
)

@bot.event
async def event_ready():
    print(f"✅ Connected to Twitch as {bot.nick}")

@bot.event
async def event_message(message):
    print(f"[{message.author.name}]: {message.content}")
    await bot.handle_commands(message)

@bot.command(name="ping")
async def ping_command(ctx):
    await ctx.send("Pong!")

# 🔁 This keeps the bot running and connects to Twitch IRC
bot.run()