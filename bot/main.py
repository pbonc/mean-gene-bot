from twitchio.ext import commands
from config import TWITCH_TOKEN, BOT_NICK, CHANNEL
from command_loader import load_sfx_commands
import sys
import os
sys.path.append(os.path.dirname(__file__))



class MeanGeneBot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix='!',
            initial_channels=[CHANNEL]
        )

        # Dynamically load SFX-based commands
        load_sfx_commands(self)

    async def event_ready(self):
        print(f'✅ Logged in as: {self.nick}')
        print(f'🎯 Initial Channel: {CHANNEL}')
        print(f'🛡  Bot Nick: {BOT_NICK}')
        print(f'🔌 Connected Channels: {self.connected_channels}')

    async def event_message(self, message):
        if message.echo:
            return

        print(f"[{message.author.name}]: {message.content}")
        await self.handle_commands(message)

    @commands.command(name='ping')
    async def ping_command(self, ctx):
        await ctx.send('pong')


if __name__ == "__main__":
    bot = MeanGeneBot()
    bot.run()
