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

class SFXComponent(commands.Component):
    def __init__(self, bot):
        self.bot = bot
        self.sfx_commands = {}  # command_name: (file_path, sfx_type, extra)
        self.executor = ThreadPoolExecutor(max_workers=1)  # Single worker for sequential playback
        self.logger = logging.getLogger("sfx")
        self._registered = set()  # set of command names we've registered as Twitch commands
        
        # Playback queue for sequential SFX playback
        self.playback_queue = asyncio.Queue()
        self._playback_task = None

        # Immediate initial scan (no print)
        scan = self._scan_sfx_files()
        for cmd, info in scan.items():
            self._register_sfx_command(cmd, info)
        self.sfx_commands = scan

    async def component_load(self):
        """Called when the component is loaded - start background tasks here"""
        # Start the async watcher and playback processor
        async def delayed_start():
            await asyncio.sleep(2)
            await self._watch_sfx_folder()
        try:
            # Use asyncio.create_task for the background tasks
            asyncio.create_task(delayed_start())
            # Start the playback queue processor
            self._playback_task = asyncio.create_task(self._process_playback_queue())
        except Exception as e:
            print(f"[SFX] Failed to start background task: {e}")

    async def component_teardown(self):
        """Called when the component is being unloaded"""
        if self._playback_task and not self._playback_task.done():
            self._playback_task.cancel()

    async def _process_playback_queue(self):
        """Process the playback queue, playing one sound at a time"""
        while True:
            try:
                # Wait for the next sound to play
                sound_path = await self.playback_queue.get()
                
                # Play the sound and wait for it to complete
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(self.executor, playsound, sound_path)
                
                # Mark this task as done
                self.playback_queue.task_done()
                
            except asyncio.CancelledError:
                # Component is being torn down
                break
            except Exception as e:
                self.logger.error(f"Error playing sound: {e}")
                # Continue processing the queue even if one sound fails
                try:
                    self.playback_queue.task_done()
                except ValueError:
                    pass

    async def _watch_sfx_folder(self):
        prev_snapshot = dict(self.sfx_commands)
        # Check if bot has the method, use it if available
        if hasattr(self.bot, 'wait_until_ready'):
            await self.bot.wait_until_ready()
        elif hasattr(self.bot, 'wait_for_ready'):
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
        
        # Create a dynamic command function that handles case-insensitive matching
        async def sfx_player(ctx):
            # Check if the command was triggered with different casing
            command_used = ctx.message.content.split()[0][1:].lower()  # Remove ! and lowercase
            await self._handle_sfx_command(ctx, command_used)
        
        sfx_player.__name__ = f"sfx_cmd_{cmd}"
        try:
            self.bot.remove_command(cmd)
        except Exception:
            pass
        self.bot.add_command(commands.Command(sfx_player, name=cmd))
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
        """Add a sound to the playback queue for sequential playback"""
        await self.playback_queue.put(path)

    async def _announce_new_command(self, cmd, info):
        sfx_type = info[1]
        extra = info[2]
        if sfx_type == "flat":
            msg = f"SFX command !{cmd} is now available!"
        elif sfx_type == "folderfile":
            msg = f"SFX command !{cmd} (from {extra}) is now available!"
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
    bot.load_component(SFXComponent(bot))