import os
import asyncio
import hashlib
import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()


try:
    from twitchio.ext import commands
    print("✅ Imported twitchio.commands")
except Exception as e:
    print("❌ Failed to import twitchio:", e)
    traceback.print_exc()

try:
    from config import TWITCH_TOKEN, BOT_NICK, CHANNEL
    print("✅ Imported config values")
except Exception as e:
    print("❌ Failed to import config.py:", e)
    traceback.print_exc()

try:
    from command_loader import load_sfx_commands, is_valid_command_name, log_skip
    print("✅ Imported command_loader")
except Exception as e:
    print("❌ Failed to import command_loader:", e)
    traceback.print_exc()

BOT_VERSION = "1.2.0a"

# Setup crash logging
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "mean-gene-bot-crash.log"),
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

class MeanGeneBot(commands.Bot):

    def __init__(self):
        print("🔧 Initializing MeanGeneBot...")
        super().__init__(
            token=TWITCH_TOKEN,
            prefix='!',
            initial_channels=[CHANNEL]
        )
        print("📦 Loading SFX commands...")
        load_sfx_commands(self)
        self.sfx_task = None

    async def event_ready(self):
        print(f'✅ Logged in as: {self.nick}')
        print(f'🎯 Initial Channel: {CHANNEL}')
        print(f'🛡  Bot Nick: {BOT_NICK}')
        print(f'🔌 Connected Channels: {self.connected_channels}')

        for chan in self.connected_channels:
            await chan.send("Welcome to the main event!")

        self.sfx_task = self.loop.create_task(self.watch_sfx_folder())

    async def event_message(self, message):
        if message.echo or message.author.name.lower() == BOT_NICK.lower():
            return

        print(f"[{message.author.name}]: {message.content}")
        await self.handle_commands(message)

    async def event_command_error(self, ctx, error):
        if isinstance(error, commands.errors.CommandNotFound):
            full_message = ctx.message.content.strip()
            if not full_message.startswith("!"):
                return

            attempted = full_message[1:].split()[0]
            user = ctx.author.name
            user_info = await self.fetch_users(names=[user])
            created = user_info[0].created_at.replace(tzinfo=None) if user_info and user_info[0].created_at else None

            reason = "invalid characters in command" if not is_valid_command_name(attempted) else "command not found"
            log_skip(reason, user, attempted, created)

    async def watch_sfx_folder(self):
        print("👀 Watching SFX folder...")
        last_hash = self.hash_sfx_directory()
        while True:
            await asyncio.sleep(30)
            new_hash = self.hash_sfx_directory()
            if new_hash != last_hash:
                from command_loader import load_sfx_commands
                load_sfx_commands(self)
                last_hash = new_hash
                for chan in self.connected_channels:
                    await chan.send("SFX folder updated.")

    def hash_sfx_directory(self, sfx_path="sfx"):
        hasher = hashlib.sha256()
        for root, _, files in os.walk(sfx_path):
            for f in sorted(files):
                path = os.path.join(root, f)
                hasher.update(path.encode())
                hasher.update(str(os.path.getmtime(path)).encode())
        return hasher.hexdigest()

    async def event_error(self, error: Exception, data=None):
        logging.error("Unhandled exception", exc_info=error)
        print("\n💥 Unhandled exception in event loop:")
        print(traceback.format_exc())

        if self.sfx_task:
            self.sfx_task.cancel()

        try:
            for chan in self.connected_channels:
                await chan.send("Raz... tired...")
        except Exception as e:
            print(f"⚠️ Failed to send crash message: {e}")

    @commands.command(name='botver')
    async def botver_command(self, ctx):
        await ctx.send(f"Mean Gene Bot version {BOT_VERSION}")

if __name__ == "__main__":
    try:
        print("🛠 Constructing MeanGeneBot...")
        bot = MeanGeneBot()
        print("🚀 Running bot...")
        bot.run()
    except Exception as e:
        print("💥 Bot failed to start.")
        print(e)
        traceback.print_exc()
