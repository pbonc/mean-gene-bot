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
        self.initialized = False  # Track if startup scan is complete
        # Maps folder_name -> set of filenames (just filename, not full path)
        self.folder_randomizer_files = dict()

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

                current_sfx, folder_files = self._get_sfx_commands_and_folder_files()
                added = current_sfx - self.known_commands
                removed = self.known_commands - current_sfx

                # --- File membership in randomizer folders ---
                if self.initialized:
                    # Detect file additions/removals inside randomizer folders
                    for folder, files in folder_files.items():
                        prev_files = self.folder_randomizer_files.get(folder, set())
                        added_files = files - prev_files
                        removed_files = prev_files - files
                        for fname in added_files:
                            cmd = f"!{os.path.splitext(fname)[0]}"
                            await self._send_twitch_msg(f"!{folder} command updated: {cmd} added")
                        for fname in removed_files:
                            cmd = f"!{os.path.splitext(fname)[0]}"
                            await self._send_twitch_msg(f"!{folder} command updated: {cmd} removed")
                    self.folder_randomizer_files = folder_files  # update for next tick

                    # Register/unregister SFX commands
                    for sfx in added:
                        register_sfx_command(self.bot, sfx)
                        await self._send_twitch_msg(f"New SFX command added: !{sfx}")
                    for sfx in removed:
                        unregister_sfx_command(self.bot, sfx)
                        await self._send_twitch_msg(f"SFX command removed: !{sfx}")
                else:
                    # On first run, set the folder membership baseline
                    self.folder_randomizer_files = folder_files
                    if self.verbose:
                        print(f"🌱 SFXWatcher baseline count: {len(current_sfx)}")
                self.known_commands = current_sfx
                self.initialized = True
                await asyncio.sleep(CHECK_INTERVAL)

            except asyncio.CancelledError:
                if self.verbose:
                    print("🛑 SFXWatcher task cancelled in loop.")
                break
            except Exception as e:
                print(f"⚠️ Error in SFXWatcher: {e}")
                await asyncio.sleep(CHECK_INTERVAL)

    def _get_sfx_commands_and_folder_files(self):
        """
        Returns:
            - set of all sfx command names (files and folder-randomizers)
            - dict: folder_name -> set of mp3 filenames (for randomizer folders)
        """
        sfx_commands = set()
        folder_files = dict()
        if not os.path.exists(SFX_FOLDER):
            if self.verbose:
                print(f"DEBUG: SFX_FOLDER does not exist: {SFX_FOLDER}")
            return sfx_commands, folder_files
        for root, dirs, files in os.walk(SFX_FOLDER):
            mp3s = [f for f in files if f.lower().endswith(".mp3")]
            # Add only file-based commands
            for file in mp3s:
                name = os.path.splitext(file)[0].lower()
                sfx_commands.add(name)
            # Folder randomizer logic (only if not the root sfx folder)
            if root != SFX_FOLDER and mp3s:
                folder_name = os.path.basename(root).lower()
                if folder_name not in sfx_commands:
                    sfx_commands.add(folder_name)
                # Track files in this folder for randomizer membership
                folder_files.setdefault(folder_name, set())
                for file in mp3s:
                    folder_files[folder_name].add(file)
        return sfx_commands, folder_files