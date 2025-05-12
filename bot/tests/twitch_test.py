from twitchio.ext import commands

bot = commands.Bot(
    token="oauth:YOUR_TOKEN_HERE",  # paste your token directly
    prefix="!",
    initial_channels=["iamdar"]
)

@bot.event
async def event_ready():
    print("✅ [Twitch Test] Connected to Twitch chat")

@bot.event
async def event_message(message):
    print(f"[Twitch Test] {message.author.name}: {message.content}")

bot.run()
