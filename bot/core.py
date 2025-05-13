from twitchio.ext import commands
from bot.config import TWITCH_TOKEN, CHANNEL, BOT_NICK
from bot.version import BOT_VERSION
from bot.loader import load_all
from bot import mgb_dwf
from bot.state import set_twitch_channel
import asyncio

class MeanGeneBot(commands.Bot):
    def __init__(self, sfx_debug=False):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix="!",
            initial_channels=[CHANNEL]
        )

        # Load all other bot components
        load_all(self, sfx_debug=sfx_debug)

    async def event_ready(self):
        print("🧪 event_ready() fired!")

        print(f"✅ Logged in as: {self.nick}")
        print(f"🛡️  Bot Nick: {self.nick}")
        print(f"🔌 Connected Channels: {self.connected_channels}")

        for chan in self.connected_channels:
            print(f"🔗 Joined Twitch channel: {chan.name}")
            try:
                await chan.send("Welcome to the main event!")
                print(f"✅ Sent arrival message to {chan.name}")
            except Exception as e:
                print(f"⚠️ Failed to send message to {chan.name}: {e}")

        try:
            if self.connected_channels:
                set_twitch_channel(self.connected_channels[0])
                print("🔗 Set Twitch channel in global state")

            if hasattr(mgb_dwf, "on_ready"):
                print("📡 Triggering mgb_dwf.on_ready...")
                asyncio.run_coroutine_threadsafe(mgb_dwf.on_ready(), mgb_dwf.DISCORD_CLIENT.loop)
            else:
                print("⚠️ mgb_dwf.on_ready not found")
        except Exception as e:
            print(f"❌ Error while calling mgb_dwf.on_ready: {e}")

        print("🎉 event_ready() completed without errors")

    async def event_message(self, message):
        if message.echo or message.author.name.lower() == self.nick.lower():
            return

        if message.content.startswith("!"):
            parts = message.content.split()
            parts[0] = parts[0].lower()
            message.content = " ".join(parts)

        print(f"[{message.author.name}]: {message.content}")
        await self.handle_commands(message)

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
