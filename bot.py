from twitchio.ext import commands
from bot.config import TWITCH_TOKEN, CHANNEL, BOT_NICK
from bot.version import BOT_VERSION
from bot.loader import load_all

class MeanGeneBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix="!",
            initial_channels=[CHANNEL]
        )
        load_all(self)

    async def event_command_error(self, ctx, error):
        from bot.data.command_loader import is_valid_command_name, log_skip

        if isinstance(error, commands.errors.CommandNotFound):
            full_message = ctx.message.content.strip()
            if not full_message.startswith("!"):
                return
            attempted = full_message[1:].split()[0].lower()
            user = ctx.author.name
            user_info = await self.fetch_users(names=[user])
            created = user_info[0].created_at.replace(tzinfo=None) if user_info and user_info[0].created_at else None
            reason = "invalid characters in command" if not is_valid_command_name(attempted) else "command not found"
            log_skip(reason, user, attempted, created)

    async def event_error(self, error: Exception, data=None):
        import logging, traceback
        logging.error("Unhandled exception", exc_info=error)
        print("\n💥 Unhandled exception in event loop:")
        if error:
            print(traceback.format_exc())
        else:
            print("Unknown error occurred with no exception object.")

        try:
            for chan in self.connected_channels:
                await chan.send("Raz... tired...")
        except Exception as e:
            print(f"⚠️ Failed to send crash message: {e}")

    @commands.command(name='botver')
    async def botver_command(self, ctx):
        await ctx.send(f"Mean Gene Bot version {BOT_VERSION}")
