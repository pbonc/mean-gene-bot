import os
import asyncio
from twitchio.ext import commands
from bot.sfx_player import queue_sfx
from bot.loader import register_sfx_command

SFX_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sfx"))
CHECK_INTERVAL = 45  # seconds

class SFXWatcher:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.known_commands = set()
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self._watch_sfx_folder())
        print("🧪 SFXWatcher task was launched.")

    def stop(self):
        if self.task:
            self.task.cancel()
            print("🛑 SFXWatcher task cancelled via stop().")

    async def _watch_sfx_folder(self):
        await asyncio.sleep(5)
        print("🚀 Entered _watch_sfx_folder()")

        while True:
            try:
                print("🔁 SFXWatcher tick — scanning for changes...")

                current_sfx = self._get_sfx_commands()
                new_sfx = current_sfx - self.known_commands

                if new_sfx:
                    print(f"📦 Detected new SFX files: {new_sfx}")
                    for sfx in new_sfx:
                        register_sfx_command(self.bot, sfx)
                        print(f"✅ Registered new SFX command: !{sfx}")

                    self.known_commands = current_sfx

                    if len(new_sfx) == 1:
                        await self._send_to_twitch(f"New sfx command registered: !{list(new_sfx)[0]}")
                    else:
                        await self._send_to_twitch("Multiple new sfx commands registered.")

                await asyncio.sleep(CHECK_INTERVAL)

            except asyncio.CancelledError:
                print("🛑 SFXWatcher task cancelled.")
                break
            except Exception as e:
                print(f"⚠️ Error in SFXWatcher: {e}")
                await asyncio.sleep(CHECK_INTERVAL)

    def _get_sfx_commands(self):
        sfx_commands = set()

        for root, dirs, files in os.walk(SFX_FOLDER):
            if root == SFX_FOLDER:
                for file in files:
                    if file.endswith(".mp3"):
                        name = os.path.splitext(file)[0]
                        sfx_commands.add(name.lower())
            else:
                # Subfolder command (e.g., !lenny)
                folder_name = os.path.basename(root).lower()
                if any(f.endswith(".mp3") for f in files):
                    sfx_commands.add(folder_name)

                # Individual subfolder files (e.g., !lenny2)
                for file in files:
                    if file.endswith(".mp3"):
                        name = os.path.splitext(file)[0]
                        sfx_commands.add(name.lower())

        return sfx_commands

    async def _send_to_twitch(self, message):
        chan = self.bot.get_channel(self.bot.initial_channels[0])
        if chan:
            await chan.send(message)
