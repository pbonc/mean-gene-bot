import os
from twitchio.ext import commands
from dotenv import load_dotenv

# Load .env file
load_dotenv()

TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_BOT_ID = os.getenv("TWITCH_BOT_ID")
TWITCH_CHANNELS = os.getenv("TWITCH_CHANNELS", "").split(",")

class Bot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            client_id=TWITCH_CLIENT_ID,
            prefix="!",
            initial_channels=TWITCH_CHANNELS
        )

    async def event_ready(self):
        print(f"Logged in as | {self.nick}")

    async def event_message(self, message):
        print(f"Message from {message.author.name}: {message.content}")
        await self.handle_commands(message)

    @commands.command(name='hello')
    async def hello(self, ctx):
        await ctx.send(f"Hello, {ctx.author.name}!")

if __name__ == "__main__":
    bot = Bot()
    bot.run()