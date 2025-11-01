import os
import re
import random
import asyncio
import logging
from twitchio.ext import commands
from concurrent.futures import ThreadPoolExecutor
from bot.overlay_server import broadcast_overlay_message
from PIL import Image
from typing import List, Dict
import wave
import contextlib
import math

# Optional Google Sheets sync helper (if requirements installed)
try:
    from bot.google_sheets_sync import write_full_sheet
except Exception:
    write_full_sheet = None

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


def get_audio_duration_ms(path: str):
    """Return audio duration in milliseconds for common types.

    Strategies:
    - For WAV files, use the stdlib wave module.
    - Try mutagen (if installed) for mp3/ogg and others.
    - If all else fails, return empty string.
    """
    if not path or not isinstance(path, str):
        return ""
    try:
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        if ext == ".wav":
            with contextlib.closing(wave.open(path, "r")) as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                seconds = frames / float(rate) if rate else 0
                return int(seconds * 1000)
        # try mutagen if available for mp3/ogg/etc
        try:
            # import lazily; optional dependency
            from mutagen import File as MutagenFile  # type: ignore
            m = MutagenFile(path)
            if m and hasattr(m, "info") and getattr(m.info, "length", None) is not None:
                return int(m.info.length * 1000)
        except Exception:
            # mutagen not installed or failed to read file -> skip
            pass
    except Exception:
        pass
    return ""


def get_audio_duration_seconds_truncated(path: str):
    """Return audio duration in seconds truncated to the tenth (e.g. 12.3).

    Returns a float with one decimal place, or empty string if unknown.
    """
    ms = get_audio_duration_ms(path)
    if not ms:
        return ""
    try:
        seconds = float(ms) / 1000.0
        truncated = math.floor(seconds * 10) / 10.0
        return truncated
    except Exception:
        return ""

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
                    # Sync sheet after adding a new command
                    try:
                        await self._maybe_sync_sheet()
                    except Exception:
                        self.logger.exception("Error syncing sheet after add")
            for cmd in list(prev_snapshot.keys()):
                if cmd not in snapshot:
                    self._unregister_media_command(cmd)
                    # Sync sheet after removal
                    try:
                        await self._maybe_sync_sheet()
                    except Exception:
                        self.logger.exception("Error syncing sheet after remove")
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

    def get_registered_media_command_rows(self) -> List[Dict]:
        """For a public-facing sheet we only expose two columns:

        - command_name
        - description

        The description is a short, non-sensitive summary combining whether the command
        has an overlay image (and the image filename) and whether it plays an SFX.
        """
        rows: List[Dict] = []
        for cmd, entry in self.media_commands.items():
            parts = []
            if "image" in entry:
                # image_rel is the relative path used by the overlay (folder/file.ext)
                image_rel = entry.get("image", (None, None))[1] or ""
                parts.append(f"Image: {image_rel}")
            if "sfx" in entry:
                sfx = entry.get("sfx")
                sfx_type = sfx[1]
                if sfx_type == "folder":
                    parts.append(f"SFX: {sfx[2]} (folder)")
                else:
                    # sfx[0] may be a path string
                    sfx_path = sfx[0]
                    if isinstance(sfx_path, list):
                        # shouldn't happen for non-folder types, but guard anyway
                        parts.append(f"SFX: {sfx[2]} (multiple)")
                    else:
                        parts.append(f"SFX: {os.path.splitext(os.path.basename(sfx_path))[0]}")
                        # compute duration if available for single-file SFX
                        dur_ms = get_audio_duration_ms(sfx_path)
                        # do not append duration to the public description; duration will be a separate column

            description = " | ".join(parts)

            # include duration as a separate column when available (seconds truncated to 0.1s)
            # For folder randomizers or multi-path entries this will be blank.
            sfx_duration = ""
            if "sfx" in entry:
                sfx_entry = entry.get("sfx")
                sfx_path_or_list = sfx_entry[0]
                if isinstance(sfx_path_or_list, str):
                    sfx_duration = get_audio_duration_seconds_truncated(sfx_path_or_list)

            rows.append({"command_name": cmd, "description": description, "duration": sfx_duration})
        # Sort rows so symbols come first, then letters, then numbers (both within-group sorted lexicographically)
        def _sort_key(name: str):
            if not name:
                return (3, "")
            first = name[0]
            if first.isalpha():
                cat = 1
            elif first.isdigit():
                cat = 2
            else:
                cat = 0
            return (cat, name.lower())

        rows.sort(key=lambda r: _sort_key(r.get("command_name", "")))
        return rows

    async def _maybe_sync_sheet(self, ctx=None):
        """Attempt to sync the current media command list to Google Sheets if configured.

        This runs the blocking `write_full_sheet` in an executor to avoid blocking the event loop.
        If ctx is provided, send status messages to the channel.
        """
        json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        spreadsheet_id = os.environ.get("SFX_SPREADSHEET_ID")
        sheet_name = os.environ.get("SFX_SHEET_NAME", "sfx")
        if not write_full_sheet:
            self.logger.warning("Google Sheets sync attempted but gspread is unavailable")
            if ctx:
                await ctx.send("⚠️ Google Sheets sync is not configured (missing requirements).")
            return
        if not json_path or not spreadsheet_id:
            self.logger.warning("Google Sheets sync attempted but env vars missing")
            if ctx:
                await ctx.send("⚠️ Google Sheets sync not configured (set GOOGLE_SERVICE_ACCOUNT_JSON and SFX_SPREADSHEET_ID).")
            return

        rows = self.get_registered_media_command_rows()
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, write_full_sheet, json_path, spreadsheet_id, sheet_name, rows)
            if ctx:
                await ctx.send(f"✅ SFX sheet synced ({len(rows)} rows).")
        except Exception as e:
            self.logger.exception("Failed to sync SFX sheet: %s", e)
            if ctx:
                await ctx.send("❌ Failed to sync SFX sheet; check logs.")

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

    @commands.command(name="syncsfx")
    async def syncsfx(self, ctx):
        """Force a sync of the SFX/GIF command list to the configured Google Sheet. Mod-only."""
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only mods can force SFX sync.")
            return
        await self._maybe_sync_sheet(ctx)

def prepare(bot):
    bot.add_cog(MediaOverlayCog(bot))