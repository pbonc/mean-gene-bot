"""Persistent, moderator-managed text-only Twitch chat commands."""

import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone

from twitchio.ext import commands


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMAND_FILE = os.path.join(PROJECT_ROOT, "data", "custom_text_commands.json")
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{1,24}$")
FORBIDDEN_TEXT = re.compile(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]")
MAX_COMMANDS = 75
MAX_RESPONSE_LENGTH = 400
RESERVED_NAMES = {"baron", "cmd", "customcmd"}
GLOBAL_COOLDOWN_SECONDS = 1.5
COMMAND_COOLDOWN_SECONDS = 8.0


def _is_mod_or_broadcaster(author) -> bool:
    return bool(
        getattr(author, "is_mod", False)
        or getattr(author, "is_broadcaster", False)
    )


class CustomTextCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger("custom_text_commands")
        self.entries = self._load()
        self.registered = set()
        self.last_response_at = 0.0
        self.command_response_at = {}
        for name in list(self.entries):
            self._register(name)

    def _load(self):
        try:
            with open(COMMAND_FILE, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.error("Could not load custom commands: %s", exc)
            return {}

    def _save(self):
        os.makedirs(os.path.dirname(COMMAND_FILE), exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="custom_text_commands_", suffix=".json", dir=os.path.dirname(COMMAND_FILE)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(self.entries, handle, indent=2, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, COMMAND_FILE)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _register(self, name):
        if name in RESERVED_NAMES or self.bot.get_command(name):
            self.logger.warning("Skipping custom command !%s because that name is reserved", name)
            return False

        async def send_custom(ctx):
            entry = self.entries.get(name)
            if not entry:
                return
            now = time.monotonic()
            if now - self.last_response_at < GLOBAL_COOLDOWN_SECONDS:
                return
            if now - self.command_response_at.get(name, 0.0) < COMMAND_COOLDOWN_SECONDS:
                return
            self.last_response_at = now
            self.command_response_at[name] = now
            await ctx.send(entry["response"])

        command = commands.Command(name=name, func=send_custom)
        command._custom_text_command = True
        self.bot.add_command(command)
        self.registered.add(name)
        return True

    def _unregister(self, name):
        command = self.bot.get_command(name)
        if command and getattr(command, "_custom_text_command", False):
            self.bot.remove_command(name)
        self.registered.discard(name)

    @commands.command(name="baron")
    async def baron_command(self, ctx):
        await ctx.send(
            "Go say hi to Baron and Caerdwyn over on Picarto: https://picarto.tv/BaronEngel"
        )

    @commands.command(name="cmd", aliases=("customcmd",))
    async def manage_command(self, ctx):
        if not _is_mod_or_broadcaster(ctx.author):
            await ctx.send("Only moderators or the broadcaster can manage custom commands.")
            return

        parts = ctx.message.content.split(maxsplit=3)
        action = parts[1].lower() if len(parts) > 1 else ""
        if action == "list":
            names = sorted(self.entries)
            summary = ", ".join(f"!{name}" for name in names) or "none"
            await ctx.send(f"Custom text commands ({len(names)}/{MAX_COMMANDS}): {summary}")
            return

        if action in {"remove", "delete"}:
            if len(parts) < 3:
                await ctx.send("Usage: !cmd remove <name>")
                return
            name = parts[2].lower().lstrip("!")
            if name not in self.entries:
                await ctx.send(f"Custom command !{name} was not found.")
                return
            self._unregister(name)
            del self.entries[name]
            self._save()
            self.logger.info("!%s removed by %s", name, ctx.author.name)
            await ctx.send(f"Custom command !{name} removed.")
            return

        if action not in {"add", "edit"} or len(parts) < 4:
            await ctx.send("Usage: !cmd add <name> <text> | edit <name> <text> | remove <name> | list")
            return

        name = parts[2].lower().lstrip("!")
        response = parts[3].strip()
        if not NAME_PATTERN.fullmatch(name):
            await ctx.send("Command names must be 2-25 characters using letters, numbers, or underscores.")
            return
        if not response or len(response) > MAX_RESPONSE_LENGTH:
            await ctx.send(f"Responses must be 1-{MAX_RESPONSE_LENGTH} characters.")
            return
        if FORBIDDEN_TEXT.search(response):
            await ctx.send("Responses cannot contain control characters or hidden direction-changing text.")
            return

        exists = name in self.entries
        if action == "add" and exists:
            await ctx.send(f"!{name} already exists. Use !cmd edit {name} <text>.")
            return
        if action == "edit" and not exists:
            await ctx.send(f"!{name} does not exist. Use !cmd add {name} <text>.")
            return
        if not exists and len(self.entries) >= MAX_COMMANDS:
            await ctx.send(f"Custom command limit reached ({MAX_COMMANDS}).")
            return
        if not exists and (name in RESERVED_NAMES or self.bot.get_command(name)):
            await ctx.send(f"!{name} is reserved by an existing bot command.")
            return

        author = getattr(ctx.author, "name", "unknown")
        self.entries[name] = {
            "response": response,
            "updated_by": author,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if not exists and not self._register(name):
            del self.entries[name]
            await ctx.send(f"!{name} is reserved by an existing bot command.")
            return
        self._save()
        self.logger.info("!%s %s by %s", name, "edited" if exists else "added", author)
        await ctx.send(f"Custom command !{name} {'updated' if exists else 'created'}.")


def prepare(bot):
    if not bot.get_cog("CustomTextCog"):
        bot.add_cog(CustomTextCog(bot))
