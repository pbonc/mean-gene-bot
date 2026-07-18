"""Twitch presence adapter for the Stream RPG v2 expedition strip."""

from __future__ import annotations

import asyncio
import logging
import os

from twitchio.ext import commands

from bot.overlay_server import broadcast_overlay_message
from bot.rpg_v2.presence import ExpeditionPresenceService


logger = logging.getLogger("rpg_v2.presence")


def _minutes_from_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _author_identity(author) -> tuple[str | None, str]:
    display_name = str(getattr(author, "display_name", None) or getattr(author, "name", "")).strip()
    viewer_id = getattr(author, "id", None) or getattr(author, "_user_id", None)
    return (str(viewer_id).strip() if viewer_id else None, display_name)


class RpgPresenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        active_minutes = _minutes_from_env("RPG_V2_ACTIVE_MINUTES", 20)
        walkoff_minutes = _minutes_from_env("RPG_V2_WALKOFF_MINUTES", 45)
        if walkoff_minutes <= active_minutes:
            walkoff_minutes = active_minutes + 1
        self.service = ExpeditionPresenceService(
            active_window_seconds=active_minutes * 60,
            walkoff_window_seconds=walkoff_minutes * 60,
        )
        self._last_member_signature = None
        self._snapshot_task = self.bot.loop.create_task(self._snapshot_loop())

    def cog_unload(self):
        if self._snapshot_task and not self._snapshot_task.done():
            self._snapshot_task.cancel()

    def _member_signature(self, payload: dict) -> tuple:
        return tuple(
            (item["actor_id"], item["display_name"], item["class"], item["presence"], item["last_seen_at"])
            for item in payload.get("members", [])
        )

    async def _publish_snapshot(self, *, force: bool = False):
        payload = self.service.snapshot()
        signature = self._member_signature(payload)
        if not force and signature == self._last_member_signature:
            return False
        self._last_member_signature = signature
        await broadcast_overlay_message(payload)
        return True

    async def _snapshot_loop(self):
        while True:
            try:
                await self._publish_snapshot()
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("RPG v2 expedition snapshot failed", exc_info=True)
                await asyncio.sleep(2)

    @commands.command(name="join")
    async def join_expedition(self, ctx):
        viewer_id, display_name = _author_identity(ctx.author)
        if not display_name:
            return
        _, created = self.service.join(viewer_id, display_name)
        await self._publish_snapshot(force=True)
        if created:
            await ctx.send(f"@{display_name} joined the expedition as an Adventurer.")
        else:
            await ctx.send(f"@{display_name} returned to the expedition.")

    @commands.Cog.event()
    async def event_ready(self):
        await self._publish_snapshot(force=True)

    @commands.Cog.event()
    async def event_message(self, message):
        if getattr(message, "echo", False):
            return
        author = getattr(message, "author", None)
        if author is None:
            return
        viewer_id, display_name = _author_identity(author)
        if not display_name:
            return
        self.service.touch(viewer_id, display_name)


def prepare(bot):
    if not bot.get_cog("RpgPresenceCog"):
        bot.add_cog(RpgPresenceCog(bot))
