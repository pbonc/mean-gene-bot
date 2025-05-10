import os
import asyncio
import hashlib
import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv
from twitchio.ext import commands

from bot.config import TWITCH_TOKEN, BOT_NICK, CHANNEL
from bot.command_loader import load_sfx_commands, is_valid_command_name, log_skip
import mgb_dwf

# ⏱️ SFX folder scan interval in seconds (5 minutes)
SFX_WATCH_INTERVAL = 300

BOT_VERSION = "2.0.0a"
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "mean-gene-bot-crash.log"),
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

class MeanGeneBot(commands.Bot):
    def get_command(self, name):
        return super().get_command(name.lower())
    def __init__(self):
        print("🔧 Initializing MeanGeneBot...")
        super().__init__(
            token=TWITCH_TOKEN,
            prefix='!',
            initial_channels=[CHANNEL]
        )
        print("📦 Loading SFX commands...")
        load_sfx_commands(self, verbose="-sfx" in os.sys.argv)
        if hasattr(mgb_dwf, "load_dwf_commands"):
            mgb_dwf.load_dwf_commands(self)
        self.sfx_task = None

    async def event_ready(self):
        print(f'✅ Logged in as: {self.nick}')
        for chan in self.connected_channels:
            print(f"[DEBUG] Sending welcome message to {chan.name}")
            await chan.send("Welcome to the main event!")
        if hasattr(mgb_dwf, "on_ready"):
            print("📡 Triggering Discord on_ready hook...")
            await mgb_dwf.on_ready()
            if "-v" in os.sys.argv and hasattr(mgb_dwf, "DISCORD_CLIENT"):
                print("✅ Discord bot is connecting...")
                if hasattr(mgb_dwf.DISCORD_CLIENT, "guilds"):
                    for g in mgb_dwf.DISCORD_CLIENT.guilds:
                        print(f"🏠 Connected to Discord Guild: {g.name} (ID: {g.id})")
                        for ch in g.text_channels:
                            print(f"   # {ch.name} (ID: {ch.id})")
                            
        else:
            print("⚠️  mgb_dwf.on_ready not found — Discord bot may not be running.")
        print(f'✅ Logged in as: {self.nick}')
        print(f'🎯 Initial Channel: {CHANNEL}')
        print(f'🛡  Bot Nick: {BOT_NICK}')
        print(f'🔌 Connected Channels: {self.connected_channels}')
        for chan in self.connected_channels:
            print(f'🔗 Joined Twitch channel: {chan.name}')
        mgb_dwf.set_twitch_channel(self.connected_channels[0])
        self.sfx_task = asyncio.create_task(self.watch_sfx_folder())

    async def event_message(self, message):
        if message.echo or message.author.name.lower() == BOT_NICK.lower():
            return

        # Force lowercase for command dispatching
        if message.content.startswith("!"):
            parts = message.content.split()
            parts[0] = parts[0].lower()
            message.content = " ".join(parts)
        print(f"[{message.author.name}]: {message.content}")
        await self.handle_commands(message)

    async def event_command_error(self, ctx, error):
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

    async def watch_sfx_folder(self):
        print("👀 Watching SFX folder for changes...")
        last_hash = self.hash_sfx_directory()
        while True:
            await asyncio.sleep(SFX_WATCH_INTERVAL)
            try:
                new_hash = self.hash_sfx_directory()
                if new_hash != last_hash:
                    print("🔁 Change detected in SFX folder. Reloading commands...")
                    new_commands = load_sfx_commands(self, verbose="-sfx" in os.sys.argv)
                    last_hash = new_hash
                    for chan in self.connected_channels:
                        if new_commands:
                            for cmd in new_commands:
                                await chan.send(f"✅ New SFX command added: !{cmd}")
                        else:
                            await chan.send("🎵 SFX folder updated, but no new commands detected.")
                else:
                    print("[DEBUG] No change in SFX folder.")
            except Exception as e:
                print("💥 Exception in SFX folder watcher loop:")
                traceback.print_exc()

    def hash_sfx_directory(self, sfx_path=os.path.join(os.path.dirname(__file__), "sfx")):
        hasher = hashlib.sha256()
        for root, _, files in os.walk(sfx_path):
            for f in sorted(files):
                path = os.path.join(root, f)
                try:
                    stat = os.stat(path)
                    hasher.update(path.encode())
                    hasher.update(str(stat.st_mtime).encode())
                    hasher.update(str(stat.st_size).encode())
                except Exception as e:
                    print(f"⚠️ Failed to read file for hashing: {path} - {e}")
        return hasher.hexdigest()

    async def event_error(self, error: Exception, data=None):
        logging.error("Unhandled exception", exc_info=error)
        print("\n💥 Unhandled exception in event loop:")
        if error:
            print(traceback.format_exc())
        else:
            print("Unknown error occurred with no exception object.")
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
        traceback.print_exc()
