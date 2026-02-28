import os
import re
import random
import asyncio
import logging
import subprocess
from twitchio.ext import commands
from concurrent.futures import ThreadPoolExecutor
from bot.overlay_server import broadcast_overlay_message
from bot.command_routing import get_media_trigger_set, refresh_media_trigger_set
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

GIF_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "overlay_static"))
SFX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "sfx"))
IMAGE_EXTS = [".gif", ".jpg", ".jpeg", ".png", ".webp"]
AUDIO_EXTS = [".mp3", ".wav", ".ogg"]
SCAN_INTERVAL = 3  # seconds
MODS_FOLDER = "mods"
RESERVED_RPG_COMMANDS = {
    "ascend",
    "blessing",
    "bottle",
    "bonk",
    "brew",
    "classchange",
    "coin",
    "strike",
    "backstab",
    "bolt",
    "smite",
    "heal",
    "ohm",
    "taunt",
    "reap",
    "harvest",
    "summon",
    "stream_heal",
    "totem",
    "rez",
    "gamba",
    "corruption",
    "doom",
    "passrevenant",
    "resolvereferral",
    "sb",
    "summon_imp",
    "dragon",
    "sap",
    "deagle",
    "c4",
    "greenarrow",
    "tazer",
    "goldrpg",
    "taze",
    "teargass",
    "donut",
    "tommygun",
    "takeoff",
    "kid",
    "franklin",
    "jdam",
    "nuke",
    "scratch",
    "hairball",
    "meow",
    "pray",
    "touch",
    "expel",
    "judgement",
    "crack",
    "gun",
    "fight",
    "join",
    "embark",
    "stats",
    "skills",
    "ascend",
    "guard",
    "pickpocket",
    "transmute",
    "restore",
    "edict",
    "spawn",
    "stats",
    "skills",
    "transform",
    "gacha",
    "loottable",
    "rpgreset",
    "resetcog",
    "resetrpg",
    "refreshrpg",
    "newstream",
    "resetdailies",
}

# Audio system with volume control
from bot.main import audio_manager

def playsound_with_volume(path, volume=None):
    """Unified SFX playback using AudioManager"""
    if volume is not None:
        audio_manager.set_sfx_volume(volume)
    audio_manager.play_sfx(path)

# Alias for backwards compatibility
playsound = playsound_with_volume

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
    - Try PowerShell Windows Shell method as fallback (with strict timeout).
    - If all else fails, return empty string.
    
    IMPORTANT: PowerShell duration detection is DISABLED by default because it
    can hang the bot on problematic files. Set ENABLE_POWERSHELL_DURATION_DETECTION=true
    to enable it.
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
            # mutagen not installed or failed to read file -> try PowerShell fallback
            pass
        # Fallback: Try PowerShell Windows Shell method for MP3 files
        # NOTE: PowerShell method is DISABLED by default because it can hang the bot
        # Set ENABLE_POWERSHELL_DURATION_DETECTION=true in .env to enable
        enable_ps = os.getenv("ENABLE_POWERSHELL_DURATION_DETECTION", "false").lower() == "true"
        if enable_ps and ext in [".mp3", ".m4a", ".wma"]:
            try:
                import subprocess
                # Use a very short timeout (1 second) to prevent hanging
                ps_script = f'''
                $shell = New-Object -COMObject Shell.Application
                $folder = $shell.Namespace([System.IO.Path]::GetDirectoryName("{path}"))
                $file = $folder.ParseName([System.IO.Path]::GetFileName("{path}"))
                $duration = $folder.GetDetailsOf($file, 27)
                Write-Output $duration
                '''
                result = subprocess.run([
                    'powershell', '-WindowStyle', 'Hidden', '-Command', ps_script
                ], capture_output=True, text=True, timeout=1, creationflags=subprocess.CREATE_NO_WINDOW)
                
                if result.returncode == 0:
                    duration_str = result.stdout.strip()
                    # Parse duration string (format like "00:00:05")
                    if ':' in duration_str and len(duration_str) >= 7:
                        parts = duration_str.split(':')
                        if len(parts) >= 3:
                            hours = int(parts[0]) if parts[0].isdigit() else 0
                            minutes = int(parts[1]) if parts[1].isdigit() else 0
                            seconds = int(parts[2]) if parts[2].isdigit() else 0
                            total_seconds = hours * 3600 + minutes * 60 + seconds
                            return int(total_seconds * 1000)
            except subprocess.TimeoutExpired:
                # PowerShell is taking too long, skip duration detection to avoid hanging
                pass
            except Exception:
                # PowerShell method failed, will return empty string
                pass
    except Exception:
        pass
    return ""

def _was_duration_detected_by_powershell(path: str):
    """Check if duration was detected using PowerShell method"""
    try:
        from mutagen import File as MutagenFile
        m = MutagenFile(path)
        # If mutagen works, PowerShell wasn't needed
        if m and hasattr(m, "info") and getattr(m.info, "length", None) is not None:
            return False
        # If mutagen failed and we're here, PowerShell was likely used
        return True
    except Exception:
        # If mutagen import fails, PowerShell was used
        return True

def get_audio_duration_seconds_truncated(path: str):
    """Return audio duration in seconds with conservative rounding.

    Returns a float rounded UP to ensure we don't cut off sounds, or empty string if unknown.
    """
    ms = get_audio_duration_ms(path)
    if not ms:
        return ""
    try:
        seconds = float(ms) / 1000.0
        # Round UP to next tenth to ensure we don't cut sounds short
        rounded_up = math.ceil(seconds * 10) / 10.0
        return rounded_up
    except Exception:
        return ""

class MediaOverlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("media_overlay")
        self._registered = set()
        self.media_commands = {}  # cmd: {"image": (path, fname), "sfx": (path, ...)}
        self.executor = ThreadPoolExecutor(max_workers=2)
        # Note: SFX queue removed - audio_manager now handles queuing internally
        bot.loop.create_task(self._watch_media_folders()) 

    def _is_generated_media_command(self, cmd: str) -> bool:
        existing = self.bot.get_command(cmd)
        if not existing:
            return False
        callback = getattr(existing, "callback", None) or getattr(existing, "_callback", None)
        callback_name = getattr(callback, "__name__", "") if callback else ""
        return callback_name.startswith("media_cmd_")

    def _should_skip_registration(self, cmd: str) -> bool:
        routing = get_media_trigger_set()
        return cmd in RESERVED_RPG_COMMANDS or cmd in routing

    def _cleanup_reserved_command_conflicts(self):
        for cmd in RESERVED_RPG_COMMANDS:
            if self._is_generated_media_command(cmd):
                try:
                    self.bot.remove_command(cmd)
                    self.logger.info("Cleaned up generated media command !%s to preserve reserved RPG names", cmd)
                except Exception:
                    pass
                self._registered.discard(cmd)

    def cog_unload(self):
        for cmd in list(self._registered):
            self._unregister_media_command(cmd)
        self._cleanup_reserved_command_conflicts()
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass


    async def _watch_media_folders(self):
        await self.bot.wait_for_ready()
        self._cleanup_reserved_command_conflicts()
        # initial scan in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        snapshot = await loop.run_in_executor(self.executor, self._scan_media_commands)
        for cmd, entry in snapshot.items():
            self._register_media_command(cmd, entry)
        self.media_commands = snapshot

        prev_snapshot = dict(self.media_commands)
        while True:
            # Scan in executor thread to prevent event loop blocking when files are added
            snapshot = await loop.run_in_executor(self.executor, self._scan_media_commands)
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
        """Scan for media commands with a timeout to prevent indefinite hangs."""
        import signal
        
        # Use signal alarm as timeout (Unix-like systems only; Windows will skip)
        def timeout_handler(signum, frame):
            raise TimeoutError("Media command scan exceeded timeout")
        
        timeout_seconds = 30  # 30 second timeout for the entire scan
        
        # Set timeout only on Unix-like systems (not Windows)
        old_handler = None
        if hasattr(signal, 'SIGALRM'):
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
        
        try:
            return self._scan_media_commands_impl()
        except TimeoutError:
            self.logger.error("Media command scan exceeded timeout limit; returning partial results")
            return {}
        except Exception as e:
            self.logger.exception(f"Unexpected error during media command scan: {e}")
            return {}
        finally:
            # Disable timeout
            if hasattr(signal, 'SIGALRM') and old_handler is not None:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
    
    def _scan_media_commands_impl(self):
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
            # 1. Flat audio files at root (including mods.mp3)
            for entry in os.scandir(SFX_ROOT):
                if entry.is_file() and any(entry.name.lower().endswith(ext) for ext in AUDIO_EXTS):
                    name, ext = os.path.splitext(entry.name)
                    cmd = map_filename_to_command(name)
                    # mod-only command if in mods folder or named mods
                    sfx_type = "modfolderfile" if name.lower() == "mods" else "flat"
                    sfxs[cmd] = (entry.path, sfx_type, entry.name)
                elif entry.is_dir():
                    # 2. Scan subfolders for additional SFX (e.g., fe/, inuyasha/, mods/)
                    folder_name = entry.name.lower()
                    folder_path = entry.path
                    file_paths = []
                    for subentry in os.scandir(folder_path):
                        if subentry.is_file() and any(subentry.name.lower().endswith(ext) for ext in AUDIO_EXTS):
                            file_paths.append(subentry.path)
                            # Register individual file commands
                            name, ext = os.path.splitext(subentry.name)
                            file_cmd = map_filename_to_command(name)
                            sfx_type = "modfile" if folder_name == MODS_FOLDER else "file"
                            sfxs[file_cmd] = (subentry.path, sfx_type, subentry.name)
                    if file_paths:
                        # Only register folder command if not mods folder
                        if folder_name != MODS_FOLDER:
                            cmd = folder_name
                            sfx_type = "folder"
                            sfxs[cmd] = (file_paths, sfx_type, folder_name)
        except Exception as e:
            self.logger.warning(f"SFX dir not found or error scanning: {e}")

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
        existing = self.bot.get_command(cmd)
        if existing:
            callback = getattr(existing, "callback", None) or getattr(existing, "_callback", None)
            callback_name = getattr(callback, "__name__", "") if callback else ""
            if not callback_name.startswith("media_cmd_"):
                self.logger.debug(f"Skipping media command !{cmd}; command already exists and is not media-generated")
                return
        async def media_player(ctx):
            # SFX permissions and selection logic
            if "sfx" in entry:
                path_or_paths, sfx_type, extra = entry["sfx"]
                is_mod_command = sfx_type in ("modfolderfile", "modfile")
                # Permission check for mod-only sfx
                if is_mod_command and not (ctx.author.is_mod or ctx.author.is_broadcaster):
                    await ctx.send(f"@{ctx.author.name}, this is a mod level command.")
                    return
                # Folder randomizer
                if sfx_type == "folder":
                    chosen_path = random.choice(path_or_paths)
                    chosen_name = os.path.splitext(os.path.basename(chosen_path))[0].lower()
                    # Play SFX via audio_manager (queues internally)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, audio_manager.play_sfx, chosen_path)
                    await ctx.send(f"Played: !{chosen_name}")
                else:
                    name = os.path.splitext(os.path.basename(path_or_paths))[0].lower()
                    # Play SFX via audio_manager (queues internally)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, audio_manager.play_sfx, path_or_paths)
                    await ctx.send(f"Played: !{name}")
                # ZAP trigger for SFX commands
                raffle_cog = self.bot.get_cog("RaffleCog")
                if raffle_cog:
                    try:
                        await raffle_cog.trigger_zap_sfx(ctx.author.name, ctx)
                    except Exception:
                        pass
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
                # ZAP trigger for GIF-only commands
                raffle_cog = self.bot.get_cog("RaffleCog")
                if raffle_cog and "sfx" not in entry:  # avoid double trigger when command has both
                    try:
                        await raffle_cog.trigger_zap_gif(ctx.author.name, ctx)
                    except Exception:
                        pass
        media_player.__name__ = f"media_cmd_{cmd}"
        # For reserved RPG/overlap names, keep the entry but do not register a bot command
        # (RPG cog or dispatcher will invoke play_media_command directly).
        if self._should_skip_registration(cmd):
            self.media_commands[cmd] = entry
            self._registered.discard(cmd)
            self.logger.info("Skipped registration for overlapping command: !%s", cmd)
            return

        try:
            self.bot.remove_command(cmd)
        except Exception:
            pass
        self._registered.discard(cmd)
        self.bot.add_command(commands.Command(name=cmd, func=media_player))
        self._registered.add(cmd)
        self.logger.info(f"Registered media overlay command: !{cmd}")

    async def play_media_command(self, cmd: str, ctx) -> bool:
        entry = self.media_commands.get(cmd)
        if not entry:
            return False
        if "sfx" in entry:
            path_or_paths, sfx_type, extra = entry["sfx"]
            is_mod_command = sfx_type in ("modfolderfile", "modfile")
            if is_mod_command and not (ctx.author.is_mod or ctx.author.is_broadcaster):
                return False
            if sfx_type == "folder":
                chosen_path = random.choice(path_or_paths)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, audio_manager.play_sfx, chosen_path)
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, audio_manager.play_sfx, path_or_paths)
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
        return True

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
            # Add a 30-second timeout to prevent hanging during sheet sync
            await asyncio.wait_for(
                loop.run_in_executor(None, write_full_sheet, json_path, spreadsheet_id, sheet_name, rows),
                timeout=30.0
            )
            if ctx:
                await ctx.send(f"✅ SFX sheet synced ({len(rows)} rows).")
        except asyncio.TimeoutError:
            self.logger.error("Google Sheets sync timed out after 30 seconds")
            if ctx:
                await ctx.send("❌ SFX sheet sync timed out; check your network/Google Drive.")
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
        
        # Safely announce to connected channels with a short timeout
        try:
            channels_to_announce = list(self.bot.connected_channels) if hasattr(self.bot, 'connected_channels') else []
        except Exception as e:
            self.logger.warning(f"Failed to get connected channels for announcement: {e}")
            channels_to_announce = []
        
        for channel in channels_to_announce:
            try:
                # Use a timeout to prevent hanging on a single channel
                await asyncio.wait_for(channel.send(msg), timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning(f"Announcement to channel timed out for command {cmd}")
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
            path = entry["sfx"][0]
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, audio_manager.play_sfx, path)
            await ctx.send(f"Played: !{cmd}")
        elif sfx_type == "folder":
            paths = entry["sfx"][0]
            chosen_path = random.choice(paths)
            chosen_name = os.path.splitext(os.path.basename(chosen_path))[0].lower()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, audio_manager.play_sfx, chosen_path)
            await ctx.send(f"Played: !{chosen_name}")
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

    @commands.command(name="sfx")
    async def sfx_help(self, ctx, *, args=None):
        """
        Explains how SFX commands work and shows available numbered SFX files.
        Usage: !sfx
        """
        if args:
            # User tried !sfx [something] - explain the correct usage
            await ctx.send(f"❌ SFX files are individual commands, not numbers. Try !{args} if that file exists, or use !sfx to see numbered options.")
            return
            
        # Get all numbered SFX commands (files that start with digits)
        numbered_sfx = []
        for cmd, entry in self.media_commands.items():
            if "sfx" in entry and entry["sfx"][1] in ("flat", "folderfile") and cmd[0].isdigit():
                numbered_sfx.append(cmd)
        
        if numbered_sfx:
            numbered_sfx.sort(key=lambda x: int(''.join(filter(str.isdigit, x))))  # Sort numerically
            numbered_list = ", ".join([f"!{cmd}" for cmd in numbered_sfx[:20]])  # Show first 20
            if len(numbered_sfx) > 20:
                numbered_list += f" ... and {len(numbered_sfx) - 20} more"
            await ctx.send(f"🔊 SFX commands are individual (e.g., !magic, !damn). Numbered SFX: {numbered_list}")
        else:
            await ctx.send("🔊 SFX commands are individual (e.g., !magic, !damn). Use !randomsfx for a random sound or !sfxcount for total count.")

    @commands.command(name="syncsfx")
    async def syncsfx(self, ctx):
        """Force a sync of the SFX/GIF command list to the configured Google Sheet. Mod-only."""
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only mods can force SFX sync.")
            return
        await self._maybe_sync_sheet(ctx)

    @commands.command(name="sfxvolume")
    async def sfx_volume(self, ctx, level: int = None):
        """
        Set or check SFX volume level (0-100). Mod-only.
        Usage: !sfxvolume [0-100]
        """
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only mods can control SFX volume.")
            return
        
        if level is None:
            # Show current volume
            current = int(audio_manager.sfx_volume * 100)
            await ctx.send(f"🔊 Current SFX volume: {current}%")
            return
        
        if not (0 <= level <= 100):
            await ctx.send("❌ Volume must be between 0 and 100.")
            return
        
        # Update SFX volume in audio_manager
        audio_manager.set_sfx_volume(level / 100.0)
        await ctx.send(f"🔊 SFX volume set to {level}%")

    @commands.command(name="play")
    async def play_media_dispatch(self, ctx, name: str = None):
        if not name:
            await ctx.send("Usage: !play <command>")
            return
        cmd = name.strip().lower()
        played = await self.play_media_command(cmd, ctx)
        if not played:
            await ctx.send(f"No media found for !{cmd}")

    @commands.command(name="mediascan")
    async def mediascan(self, ctx):
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only mods can rescan media.")
            return
        loop = asyncio.get_event_loop()
        snapshot = await loop.run_in_executor(self.executor, self._scan_media_commands)
        prev = set(self.media_commands.keys())
        new = set(snapshot.keys())
        added = new - prev
        removed = prev - new
        for cmd in snapshot:
            self._register_media_command(cmd, snapshot[cmd])
        for cmd in list(self._registered):
            if cmd not in snapshot:
                self._unregister_media_command(cmd)
        self.media_commands = snapshot
        refresh_media_trigger_set()
        await ctx.send(f"Media scan complete. Added {len(added)}, removed {len(removed)}.")


def prepare(bot):
    bot.add_cog(MediaOverlayCog(bot))