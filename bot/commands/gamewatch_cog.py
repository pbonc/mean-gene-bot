"""Moderator-controlled live sports score announcements."""

import asyncio
import logging
import time

from twitchio.ext import commands

from bot.commands.tts_cog import _speak_text_with_voice
from bot.gamewatch import (
    format_listing, format_update, is_watchable, mlb_updates, should_announce,
)
from bot.sports_api import SportsAPIManager


LOGGER = logging.getLogger("gamewatch")
POLL_SECONDS = 30


def _is_mod_or_broadcaster(author):
    return bool(getattr(author, "is_mod", False) or getattr(author, "is_broadcaster", False))


class GameWatchCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sports = SportsAPIManager()
        self.catalog = []
        self.number_by_id = {}
        self.next_number = 1
        self.watched_id = None
        self.watched_game = None
        self.channel = None
        self.tts_enabled = False
        self.poll_task = None
        self.last_announced_game = None
        self.last_announcement_at = 0.0

    async def _available_games(self):
        games = await self.sports.fetch_gamewatch_games()
        self.catalog = [game for game in games if is_watchable(game)]
        for game in self.catalog:
            if game["id"] not in self.number_by_id:
                self.number_by_id[game["id"]] = self.next_number
                self.next_number += 1
            game["watch_number"] = self.number_by_id[game["id"]]
        self.catalog.sort(key=lambda game: game["watch_number"])
        return self.catalog

    @commands.command(name="gamewatch")
    async def gamewatch_command(self, ctx):
        if not _is_mod_or_broadcaster(ctx.author):
            await ctx.send("Only moderators or the broadcaster can use GameWatch.")
            return
        args = ctx.message.content.split()[1:]
        if args and args[0].lower() == "stop":
            self._stop()
            await ctx.send("GameWatch stopped.")
            return
        if args and args[0].lower() == "status":
            if not self.watched_game:
                await ctx.send("GameWatch is idle. Use !gamewatch to list watchable games.")
            else:
                suffix = " TTS enabled." if self.tts_enabled else ""
                await ctx.send(f"Watching: {format_update(self.watched_game)}{suffix}")
            return
        if args and args[0].isdigit():
            await self._select(ctx, int(args[0]), len(args) > 1 and args[1].lower() == "tts")
            return
        if args:
            await ctx.send("Usage: !gamewatch | !gamewatch <number> [tts] | !gamewatch status | stop")
            return
        await self._list(ctx)

    async def _list(self, ctx):
        try:
            games = await self._available_games()
        except Exception as exc:
            LOGGER.exception("Could not build GameWatch catalog")
            await ctx.send(f"GameWatch could not reach the sports service: {type(exc).__name__}.")
            return
        if not games:
            await ctx.send("GameWatch: no games are live or within 15 minutes of their scheduled start.")
            return
        listings = [format_listing(game, game["watch_number"]) for game in games]
        for offset in range(0, len(listings), 3):
            await ctx.send("GameWatch available: " + " | ".join(listings[offset:offset + 3]))

    async def _select(self, ctx, number, tts_enabled):
        try:
            games = await self._available_games()
        except Exception as exc:
            LOGGER.exception("Could not refresh GameWatch catalog")
            await ctx.send(f"GameWatch could not reach the sports service: {type(exc).__name__}.")
            return
        selected = next((game for game in games if game["watch_number"] == number), None)
        if selected is None:
            await ctx.send("That game number is not currently watchable. Run !gamewatch for a fresh list.")
            return
        self._stop()
        self.watched_game = selected
        if self.watched_game["sport"] == "MLB" and self.watched_game.get("state") == "in":
            self.watched_game = await self.sports.enrich_gamewatch_mlb(self.watched_game)
        self.watched_id = self.watched_game["id"]
        self.channel = ctx.channel
        self.tts_enabled = tts_enabled
        self.last_announced_game = dict(self.watched_game)
        self.last_announcement_at = time.monotonic()
        self.poll_task = self.bot.loop.create_task(self._poll())
        suffix = " with TTS" if tts_enabled else ""
        await ctx.send(f"GameWatch started{suffix}: {format_update(self.watched_game)}")

    def _stop(self):
        task = self.poll_task
        self.poll_task = None
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if task and not task.done() and task is not current_task:
            task.cancel()
        self.watched_id = None
        self.watched_game = None
        self.channel = None
        self.tts_enabled = False
        self.last_announced_game = None

    async def _poll(self):
        while self.watched_id:
            await asyncio.sleep(POLL_SECONDS)
            try:
                games = await self.sports.fetch_gamewatch_games()
                current = next((game for game in games if game["id"] == self.watched_id), None)
                if not current:
                    LOGGER.warning("Watched game %s missing from scoreboard", self.watched_id)
                    continue
                if current["sport"] == "MLB":
                    current = await self.sports.enrich_gamewatch_mlb(current)
                self.watched_game = current
                elapsed = time.monotonic() - self.last_announcement_at
                if current["sport"] == "MLB":
                    messages = mlb_updates(self.last_announced_game, current)
                elif should_announce(self.last_announced_game, current, elapsed):
                    messages = [format_update(current)]
                else:
                    messages = []
                for message in messages:
                    await self.channel.send(message)
                    if self.tts_enabled:
                        await _speak_text_with_voice(message, None)
                if messages:
                    self.last_announced_game = dict(current)
                    self.last_announcement_at = time.monotonic()
                elif current["sport"] == "MLB":
                    # Pitcher changes and milestones compare against the last poll,
                    # while NBA deliberately accumulates against its last announcement.
                    self.last_announced_game = dict(current)
                if current.get("completed"):
                    self._stop()
                    return
            except asyncio.CancelledError:
                return
            except Exception:
                LOGGER.exception("GameWatch polling failed; will retry")

    def cog_unload(self):
        self._stop()


def prepare(bot):
    if not bot.get_cog("GameWatchCog"):
        bot.add_cog(GameWatchCog(bot))
