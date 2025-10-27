import os
import re
import random
import asyncio
import logging
from twitchio.ext import commands
from concurrent.futures import ThreadPoolExecutor
from bot.overlay_server import broadcast_overlay_message
from PIL import Image

GIF_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "overlay_static", "gifs"))
SFX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "sfx"))
IMAGE_EXTS = [".gif", ".jpg", ".jpeg", ".png", ".webp"]
AUDIO_EXTS = [".mp3", ".wav", ".ogg"]
SCAN_INTERVAL = 3  # seconds
MODS_FOLDER = "mods"

try:
    from playsound import playsound
except ImportError:
    def playsound(path): print(f"Would play sound: {path}")

def map_filename_to_command(filename):
    base = filename
    m = re.match(r"^(.*)heart(\d*)$", base)
    if m:
        prefix = m.group(1)
        number = m.group(2) or ""
        return f"{prefix}<3{number}"
    return base

def get_gif_duration_ms(path):
    try:
        with Image.open(path) as im:
            if getattr(im, "is_animated", False):
                durations = []
                for frame in range(im.n_frames):
                    im.seek(frame)
                    durations.append(im.info.get("duration", 0))
                total = sum(durations)
                return total if total > 0 else 5000
    except Exception:
        pass
    return 5000

class MediaOverlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("media_overlay")
        self._registered = set()
        self.media_commands = {}  # cmd: {"image": (path, fname), "sfx": (path, ...)}
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.sfx_queue = asyncio.Queue()
        bot.loop.create_task(self._sfx_queue_worker())
        bot.loop.create_task(self._watch_media_folders()) 


    async def _sfx_queue_worker(self):
        while True:
            play_item = await self.sfx_queue.get()  # (path, ctx, message)
            path, ctx, message = play_item
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(self.executor, playsound, path)
                if message and ctx:
                    await ctx.send(message)
            except Exception as e:
                if ctx:
                    await ctx.send("❌ Error playing SFX.")
                self.logger.error(f"Error playing SFX: {e}")
            self.sfx_queue.task_done()

    async def _watch_media_folders(self):
        await self.bot.wait_for_ready()
        # initial scan
        snapshot = self._scan_media_commands()
        for cmd, entry in snapshot.items():
            self._register_media_command(cmd, entry)
        self.media_commands = snapshot

        prev_snapshot = dict(self.media_commands)
        while True:
            snapshot = self._scan_media_commands()
            for cmd, entry in snapshot.items():
                if cmd not in prev_snapshot:
                    self._register_media_command(cmd, entry)
                    await self._announce_new_command(cmd, entry)
            for cmd in list(prev_snapshot.keys()):
                if cmd not in snapshot:
                    self._unregister_media_command(cmd)
            prev_snapshot = snapshot
            self.media_commands = snapshot
            await asyncio.sleep(SCAN_INTERVAL)

    def _scan_media_commands(self):
        # --- GIFs ---
        images = {}
        try:
            # Walk the gifs directory recursively so files in subfolders (e.g., gifs/heart/) are discovered
            for dirpath, dirnames, filenames in os.walk(GIF_ROOT):
                # relative directory under GIF_ROOT (use forward slashes for web paths)
                rel_dir = os.path.relpath(dirpath, GIF_ROOT)
                if rel_dir == ".":
                    rel_dir = ""
                else:
                    rel_dir = rel_dir.replace('\\', '/')
                for fname in filenames:
                    if not any(fname.lower().endswith(ext) for ext in IMAGE_EXTS):
                        continue
                    name, ext = os.path.splitext(fname)
                    # Start with filename-based mapping (handles names containing 'heart')
                    cmd = map_filename_to_command(name)
                    # If the filename didn't contain 'heart' but the file is inside a folder named 'heart',
                    # map the command to <3 suffix (e.g., 'dar' in gifs/heart -> 'dar<3')
                    if '<3' not in cmd and rel_dir:
                        # check each segment of rel_dir
                        segments = [s.lower() for s in rel_dir.split('/') if s]
                        if any('heart' in s for s in segments):
                            cmd = f"{name}<3"
                    # Store full filesystem path and the relative web path for the file (subfolder/name)
                    rel_fname = f"{rel_dir}/{fname}".lstrip('/') if rel_dir else fname
                    images[cmd] = (os.path.join(dirpath, fname), rel_fname)
        except Exception as e:
            self.logger.warning(f"GIF overlay dir not found: {e}")

        # --- SFXs ---
        sfxs = {}
        try:
            # 1. Flat mp3s at root (including mods.mp3)
            for entry in os.scandir(SFX_ROOT):
                if entry.is_file() and entry.name.lower().endswith(".mp3"):
                    cmd = os.path.splitext(entry.name)[0].lower()
                    sfxs[cmd] = (entry.path, "flat", None)
            # 2. Foldered sfx
            for entry in os.scandir(SFX_ROOT):
                if entry.is_dir():
                    folder_name = entry.name.lower()
                    folder_mp3s = [
                        f for f in os.scandir(entry.path)
                        if f.is_file() and f.name.lower().endswith(".mp3")
                    ]
                    if folder_mp3s:
                        if folder_name == MODS_FOLDER:
                            # Only register mod-only commands for each file in /mods, NOT the folder as a randomizer
                            for f in folder_mp3s:
                                cmd = os.path.splitext(f.name)[0].lower()
                                sfxs[cmd] = (f.path, "modfolderfile", folder_name)
                        else:
                            # Register folder randomizer
                            sfxs[folder_name] = (
                                [f.path for f in folder_mp3s],
                                "folder",
                                folder_name,
                            )
                            # And individual file commands
                            for f in folder_mp3s:
                                cmd = os.path.splitext(f.name)[0].lower()
                                sfxs[cmd] = (f.path, "folderfile", folder_name)
        except Exception as e:
            self.logger.warning(f"SFX dir not found: {e}")

        # --- Combine GIF/SFX mapping ---
        result = {}
        for cmd in set(images.keys()) | set(sfxs.keys()):
            entry = {}
            if cmd in images:
                entry["image"] = images[cmd]
            if cmd in sfxs:
                entry["sfx"] = sfxs[cmd]
            result[cmd] = entry
        return result

    def _register_media_command(self, cmd, entry):
        if cmd in self._registered:
            return
        async def media_player(ctx):
            # SFX permissions and selection logic
            if "sfx" in entry:
                path_or_paths, sfx_type, extra = entry["sfx"]
                is_mod_command = sfx_type == "modfolderfile"
                # Permission check for mod-only sfx
                if is_mod_command and not (ctx.author.is_mod or ctx.author.is_broadcaster):
                    await ctx.send(f"@{ctx.author.name}, this is a mod level command.")
                    return
                # Folder randomizer
                if sfx_type == "folder":
                    chosen_path = random.choice(path_or_paths)
                    chosen_name = os.path.splitext(os.path.basename(chosen_path))[0].lower()
                    await self.sfx_queue.put((chosen_path, ctx, f"Played: !{chosen_name}"))
                else:
                    await self.sfx_queue.put((path_or_paths, ctx, None))
            # Overlay image
            if "image" in entry:
                path, rel_fname = entry["image"]
                ext = os.path.splitext(rel_fname)[1].lower()
                url = f"/gifs/{rel_fname}"
                duration = get_gif_duration_ms(path) if ext == ".gif" else 5000
                await broadcast_overlay_message({
                    "type": "image",
                    "url": url,
                    "duration": duration
                })
        media_player.__name__ = f"media_cmd_{cmd}"
        try:
            self.bot.remove_command(cmd)
        except Exception:
            pass
        self.bot.add_command(commands.Command(name=cmd, func=media_player))
        self._registered.add(cmd)
        self.logger.info(f"Registered media overlay command: !{cmd}")

    def _unregister_media_command(self, cmd):
        if cmd in self._registered:
            try:
                self.bot.remove_command(cmd)
            except Exception:
                pass
            self._registered.remove(cmd)
            self.logger.info(f"Unregistered media overlay command: !{cmd}")

    async def _announce_new_command(self, cmd, entry):
        types = []
        if "image" in entry:
            types.append("overlay")
        if "sfx" in entry:
            if entry["sfx"][1] == "modfolderfile":
                types.append("mod-sfx")
            elif entry["sfx"][1] == "folder":
                types.append("random-sfx")
            else:
                types.append("sfx")
        msg = f"Overlay/SFX command !{cmd} is now available! ({' & '.join(types)})"
        for channel in self.bot.connected_channels:
            try:
                await channel.send(msg)
            except Exception as e:
                self.logger.warning(f"Failed to announce command {cmd} in channel: {e}")

    @commands.command(name="randomsfx")
    async def randomsfx(self, ctx):
        """
        Plays a random, public SFX command and displays which SFX was played.
        """
        # Only use public SFX: flat, folderfile, folder randomizers (not modfolderfile)
        valid_cmds = [
            (cmd, entry)
            for cmd, entry in self.media_commands.items()
            if "sfx" in entry and entry["sfx"][1] in ("flat", "folderfile", "folder")
        ]
        if not valid_cmds:
            await ctx.send("No public SFX commands are available.")
            return
        cmd, entry = random.choice(valid_cmds)
        sfx_type = entry["sfx"][1]
        if sfx_type in ("flat", "folderfile"):
            await self.sfx_queue.put((entry["sfx"][0], ctx, f"Played: !{cmd}"))
        elif sfx_type == "folder":
            paths = entry["sfx"][0]
            chosen_path = random.choice(paths)
            chosen_name = os.path.splitext(os.path.basename(chosen_path))[0].lower()
            await self.sfx_queue.put((chosen_path, ctx, f"Played: !{chosen_name}"))
        else:
            await ctx.send("❌ Unexpected error in randomsfx.")

    @commands.command(name="sfxcount")
    async def sfxcount(self, ctx):
        """
        Returns count of public sfx commands.
        Usage: !sfxcount
        """
        count = len([
            cmd for cmd, entry in self.media_commands.items()
            if "sfx" in entry and entry["sfx"][1] in ("flat", "folderfile", "folder")
        ])
        await ctx.send(f"{count} unique sound effect commands.")

def prepare(bot):
    bot.add_cog(MediaOverlayCog(bot))