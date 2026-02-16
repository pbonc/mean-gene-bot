import os
import re
import json
import asyncio
from typing import Dict, Optional, Tuple

from twitchio.ext import commands

from bot.main import audio_manager
from bot.commands.base_command import mod_only


def _workspace_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _walkin_store_path() -> str:
    return os.path.join(_workspace_root(), "data", "walkins.json")


def _ensure_store_exists() -> None:
    path = _walkin_store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"users": {}}, f, ensure_ascii=False, indent=2)


def _load_store() -> Dict:
    _ensure_store_exists()
    try:
        with open(_walkin_store_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"users": {}}
        # Normalize structure
        data.setdefault("users", {})
        return data
    except Exception:
        return {"users": {}}


def _save_store(data: Dict) -> None:
    try:
        with open(_walkin_store_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _parse_walkin_args(message_content: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse arguments from a message like:
    !walkin @username !sfxcommand "Entrance text"

    Returns (target_username_lower, sfx_command_lower, entrance_text)
    Username may be None (defaults to invoker).
    """
    # Trim leading command
    content = message_content.strip()
    # Regex to capture optional @user, required !cmd, required quoted text
    m = re.search(r"^!walkin\s+(?:@?(?P<user>[A-Za-z0-9_]+)\s+)?!(?P<cmd>[^\s\"]+)\s+\"(?P<text>[^\"]*)\"", content)
    if not m:
        return None, None, None
    user = m.group("user") if m.group("user") else None
    cmd = m.group("cmd").strip().lower() if m.group("cmd") else None
    text = m.group("text") if m.group("text") else ""
    return (user.lower() if user else None, cmd, text)


class WalkinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load and reset played statuses on startup
        self.store = _load_store()
        for u, entry in self.store.get("users", {}).items():
            if isinstance(entry, dict):
                entry["played"] = False
        _save_store(self.store)
        # Note: SFX queue removed - audio_manager now handles queuing internally

    def _get_media_overlay_cog(self):
        # Try to locate MediaOverlayCog instance among loaded cogs
        for cog in self.bot.cogs.values():
            # Avoid import cycles by checking attribute presence
            if hasattr(cog, "media_commands"):
                return cog
        return None

    def _validate_sfx_command(self, cmd: str) -> Optional[Tuple]:
        """Ensure the provided command exists and has an SFX entry.
        Returns the media entry tuple (path_or_paths, sfx_type, extra) or None.
        """
        cog = self._get_media_overlay_cog()
        if not cog:
            return None
        entry = getattr(cog, "media_commands", {}).get(cmd)
        if not entry or "sfx" not in entry:
            return None
        return entry["sfx"]

    async def _play_sfx_entry(self, sfx_entry: Tuple, text: str = "", channel = None) -> None:
        """Play an SFX entry via audio_manager (queues internally) and send text."""
        path_or_paths, sfx_type, _extra = sfx_entry
        # Select path
        if sfx_type == "folder" and isinstance(path_or_paths, list) and path_or_paths:
            import random
            path = random.choice(path_or_paths)
        else:
            path = path_or_paths
        # Queue SFX via audio_manager
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, audio_manager.play_sfx, path)
        # Send text if provided (immediately, not waiting for SFX to finish)
        if text and channel:
            try:
                await channel.send(text)
            except Exception:
                pass

    @commands.command(name="walkin")
    @mod_only
    async def walkin(self, ctx: commands.Context):
        """Set or edit a user's walk-in SFX and entrance text.
        Usage: !walkin @username !sfxcommand "Entrance text"
        - If @username is omitted, applies to the invoking user.
        - The !sfxcommand must be an existing registered SFX command.
        - Entrance text is taken between quotes (quotes excluded).
        Editing sets the played flag to unplayed for this stream.
        """
        target_user, sfx_cmd, text = _parse_walkin_args(ctx.message.content)
        if sfx_cmd is None:
            await ctx.send("Usage: !walkin @username !sfxcommand \"Entrance text\"")
            return
        # Default to invoker if no user provided
        if not target_user:
            target_user = ctx.author.name.lower()
        # Validate SFX command exists and has SFX
        sfx_entry = self._validate_sfx_command(sfx_cmd)
        if not sfx_entry:
            await ctx.send(f"❌ Unknown SFX command '!{sfx_cmd}'.")
            return
        # Save mapping and reset played flag
        users = self.store.setdefault("users", {})
        users[target_user] = {"sfx_command": sfx_cmd, "text": text, "played": False}
        _save_store(self.store)
        await ctx.send(f"✅ Walk-in set for @{target_user}: !{sfx_cmd}{' with text' if text else ''}.")

    @commands.Cog.event()
    async def event_message(self, message):
        # Trigger walk-in on first message in this stream from configured users
        try:
            author = getattr(message, "author", None)
            if not author or not getattr(author, "name", None):
                return
            username = author.name.lower()
            entry = self.store.get("users", {}).get(username)
            if not entry or not isinstance(entry, dict):
                return
            if entry.get("played", False):
                return
            # Validate command and play
            sfx_entry = self._validate_sfx_command(entry.get("sfx_command", ""))
            if not sfx_entry:
                return
            # Mark as played IMMEDIATELY to prevent race conditions
            entry["played"] = True
            _save_store(self.store)
            # Queue the SFX and text (prevents overlaps)
            text = entry.get("text", "").strip()
            await self._play_sfx_entry(sfx_entry, text, message.channel)
        except Exception:
            # Be conservative; avoid breaking chat handling
            pass


def prepare(bot: commands.Bot):
    bot.add_cog(WalkinCog(bot))
    try:
        users = len(_load_store().get("users", {}))
        print(f"[COG] WalkinCog loaded — {users} configured walk-ins")
    except Exception:
        print("[COG] WalkinCog loaded")
