import os
import asyncio
from twitchio.ext import commands
from bot.loader import register_sfx_command, unregister_sfx_command

SFX_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sfx"))
CHECK_INTERVAL = 5  # seconds

class SFXWatcher:
    def __init__(self, bot: commands.Bot, verbose=False):
        self.bot = bot
        self.known_commands = set()
        self.task = None
        self.verbose = verbose
        self.initialized = False  # <-- Track if startup scan is complete

    def start(self):
        print(f"👂 SFXWatcher START requested. Scanning folder: {SFX_FOLDER}")
        self.task = asyncio.create_task(self._watch_sfx_folder())
        if self.verbose:
            print("🧪 SFXWatcher task launched.")

    def stop(self):
        if self.task:
            self.task.cancel()
            if self.verbose:
                print("🛑 SFXWatcher task cancelled via stop().")

    async def _send_twitch_msg(self, message: str):
        # Send message to the first connected channel, adjust as needed!
        if self.bot.connected_channels:
            try:
                await self.bot.connected_channels[0].send(message)
            except Exception as e:
                print(f"⚠️ Failed to send twitch message: {e}")

    async def _watch_sfx_folder(self):
        await asyncio.sleep(2)
        if self.verbose:
            print("🚀 Entered _watch_sfx_folder()")
        while True:
            try:
                if self.verbose:
                    print("🔁 SFXWatcher tick — scanning for changes...")

                current_sfx = self._get_sfx_commands()
                added = current_sfx - self.known_commands
                removed = self.known_commands - current_sfx

                # Only announce after the initial scan
                if self.initialized:
                    for sfx in added:
                        register_sfx_command(self.bot, sfx)
                        print(f"✅ Registered new SFX command: !{sfx}")
                        await self._send_twitch_msg(f"New SFX command added: !{sfx}")

                    for sfx in removed:
                        unregister_sfx_command(self.bot, sfx)
                        print(f"❌ Unregistered SFX command: !{sfx}")
                        await self._send_twitch_msg(f"SFX command removed: !{sfx}")
                else:
                    # On first scan, just set the baseline, don't announce
                    if self.verbose:
                        print(f"🌱 SFXWatcher baseline: {current_sfx}")

                self.known_commands = current_sfx
                self.initialized = True  # After the first loop, start announcing

                await asyncio.sleep(CHECK_INTERVAL)

            except asyncio.CancelledError:
                if self.verbose:
                    print("🛑 SFXWatcher task cancelled in loop.")
                break
            except Exception as e:
                print(f"⚠️ Error in SFXWatcher: {e}")
                await asyncio.sleep(CHECK_INTERVAL)

    def _get_sfx_commands(self):
        sfx_commands = set()
        if not os.path.exists(SFX_FOLDER):
            if self.verbose:
                print(f"DEBUG: SFX_FOLDER does not exist: {SFX_FOLDER}")
            return sfx_commands
        for root, dirs, files in os.walk(SFX_FOLDER):
            mp3s = [f for f in files if f.lower().endswith(".mp3")]
            if root == SFX_FOLDER:
                for file in mp3s:
                    name = os.path.splitext(file)[0]
                    sfx_commands.add(name.lower())
            else:
                folder_name = os.path.basename(root).lower()
                if mp3s:
                    sfx_commands.add(folder_name)
                    for file in mp3s:
                        name = os.path.splitext(file)[0]
                        sfx_commands.add(name.lower())
        return sfx_commands