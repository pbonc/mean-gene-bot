from twitchio.ext import commands
from config import TWITCH_TOKEN, BOT_NICK, CHANNEL


class MeanGeneBot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix='!',
            initial_channels=[CHANNEL]
        )

    async def event_ready(self):
        print(f'✅ Logged in as | {self.nick}')

    async def event_message(self, message):
        if message.echo:
            return
        print(f"[{message.author.name}]: {message.content}")
        await self.handle_commands(message)

    @commands.command(name='ping')
    async def ping_command(self, ctx):
        await ctx.send('pong')

    # SFX stub - logic added later
    @commands.command(name='bell')
    async def bell_command(self, ctx):
        # Placeholder: actual audio trigger logic goes here
        await ctx.send(f"{ctx.author.name} rang the bell! 🔔")


if __name__ == "__main__":
    bot = MeanGeneBot()
    bot.run()
