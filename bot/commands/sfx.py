import os
import random
import asyncio
import logging
from twitchio.ext import commands
from concurrent.futures import ThreadPoolExecutor

SFX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "sfx"))
SCAN_INTERVAL = 3  # seconds

try:
    from playsound import playsound
except ImportError:
    # Fallback stub if playsound isn't installed
    def playsound(path):
        print(f"Would play sound: {path}")

class SFXCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sfx_commands = {}  # command_name: (file_path, sfx_type, extra)
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.logger = logging.getLogger("sfx")
        self._registered = set()  # set of command names we've registered as Twitch commands

        # Immediate initial scan (no print)
        scan = self._scan_sfx_files()
        for cmd, info in scan.items():
            self._register_sfx_command(cmd, info)
        self.sfx_commands = scan

        # Start the async watcher
        async def delayed_start():
            await asyncio.sleep(2)
            await self._watch_sfx_folder()
        try:
            self.bot.loop.create_task(delayed_start())
        except Exception as e:
            print(f"[SFX] Failed to start background task: {e}")

    async def _watch_sfx_folder(self):
        prev_snapshot = dict(self.sfx_commands)
        await self.bot.wait_for_ready()
        while True:
            snapshot = self._scan_sfx_files()
            # Find new commands (added)
            for cmd, info in snapshot.items():
                if cmd not in prev_snapshot:
                    print(f"[SFX] Registered new SFX command: !{cmd}")
                    self._register_sfx_command(cmd, info)
                    await self._announce_new_command(cmd, info)
            # Find removed commands
            for cmd in list(prev_snapshot.keys()):
                if cmd not in snapshot:
                    print(f"[SFX] Unregistered SFX command: !{cmd}")
                    self._unregister_sfx_command(cmd)
            prev_snapshot = snapshot
            self.sfx_commands = snapshot
            await asyncio.sleep(SCAN_INTERVAL)

    def _scan_sfx_files(self):
        result = {}
        try:
            for entry in os.scandir(SFX_ROOT):
                if entry.is_file() and entry.name.lower().endswith(".mp3"):
                    cmd = os.path.splitext(entry.name)[0].lower()
                    result[cmd] = (entry.path, "flat", None)
            for entry in os.scandir(SFX_ROOT):
                if entry.is_dir():
                    folder_name = entry.name.lower()
                    folder_mp3s = [
                        f for f in os.scandir(entry.path)
                        if f.is_file() and f.name.lower().endswith(".mp3")
                    ]
                    if folder_mp3s:
                        result[folder_name] = (
                            [f.path for f in folder_mp3s],
                            "folder",
                            folder_name,
                        )
                    for f in folder_mp3s:
                        cmd = os.path.splitext(f.name)[0].lower()
                        result[cmd] = (f.path, "folderfile", folder_name)
        except FileNotFoundError as e:
            print(f"[SFX] Error: {e}")
        return result

    def _register_sfx_command(self, cmd, info):
        if cmd in self._registered:
            return  # Already registered
        async def sfx_player(ctx):
            await self._handle_sfx_command(ctx, cmd)
        sfx_player.__name__ = f"sfx_cmd_{cmd}"
        try:
            self.bot.remove_command(cmd)
        except Exception:
            pass
        self.bot.add_command(commands.Command(name=cmd, func=sfx_player))
        self._registered.add(cmd)
        self.logger.info(f"Registered sfx command: !{cmd}")

    def _unregister_sfx_command(self, cmd):
        if cmd in self._registered:
            try:
                self.bot.remove_command(cmd)
            except Exception:
                pass
            self._registered.remove(cmd)
            self.logger.info(f"Unregistered sfx command: !{cmd}")

    async def _handle_sfx_command(self, ctx, cmd):
        info = self.sfx_commands.get(cmd)
        if not info:
            await ctx.send(f"❌ SFX not found.")
            return
        sfx_type = info[1]
        if sfx_type == "flat":
            path = info[0]
            await self._play_sound(path)
        elif sfx_type == "folderfile":
            path = info[0]
            await self._play_sound(path)
        elif sfx_type == "folder":
            paths = info[0]
            chosen_path = random.choice(paths)
            chosen_name = os.path.splitext(os.path.basename(chosen_path))[0].lower()
            await self._play_sound(chosen_path)
            await ctx.send(f"Played: !{chosen_name}")
        else:
            await ctx.send("❌ Unknown SFX type.")

    async def _play_sound(self, path):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, playsound, path)

    async def _announce_new_command(self, cmd, info):
        sfx_type = info[1]
        extra = info[2]
        if sfx_type == "flat":
            msg = f"SFX command !{cmd} is now available!"
        elif sfx_type == "folderfile":
            msg = f"SFX command !{cmd} is now available!"
        elif sfx_type == "folder":
            msg = f"SFX randomizer !{cmd} is now available!"
        else:
            msg = f"SFX command !{cmd} is now available!"
        for channel in self.bot.connected_channels:
            try:
                await channel.send(msg)
            except Exception as e:
                print(f"[SFX] Failed to announce SFX in channel {channel}: {e}")
                self.logger.warning(f"Failed to announce SFX in channel {channel}: {e}")

def prepare(bot):
    bot.add_cog(SFXCog(bot))