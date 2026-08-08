"""Moderator-controlled live sports score announcements."""

import asyncio
import logging
import time

from twitchio.ext import commands

from bot.commands.tts_cog import _speak_text_with_voice
from bot.gamewatch import (
    football_updates, format_listing, format_update, is_watchable, mlb_updates,
    should_announce,
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
        self.watches = {}
        self.poll_task = None

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
            if len(args) > 1 and args[1].isdigit():
                stopped = self._stop_number(int(args[1]))
                await ctx.send("GameWatch stopped for that game." if stopped else "That game is not being watched.")
            else:
                self._stop_all()
                await ctx.send("GameWatch stopped for all games.")
            return
        if args and args[0].lower() == "status":
            if not self.watches:
                await ctx.send("GameWatch is idle. Use !gamewatch to list watchable games.")
            else:
                for watch in self.watches.values():
                    suffix = " TTS enabled." if watch["tts"] else ""
                    await ctx.send(f"Watching {watch['number']}: {format_update(watch['game'])}{suffix}")
            return
        if args and args[0].isdigit():
            await self._select(ctx, int(args[0]), len(args) > 1 and args[1].lower() == "tts")
            return
        if args:
            await ctx.send("Usage: !gamewatch | !gamewatch <number> [tts] | !gamewatch status | !gamewatch stop [number]")
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
        if selected["sport"] == "MLB" and selected.get("state") == "in":
            selected = await self.sports.enrich_gamewatch_mlb(selected)
        self.watches[selected["id"]] = {
            "game": selected, "channel": ctx.channel, "tts": tts_enabled,
            "last": dict(selected), "last_at": time.monotonic(), "number": number,
        }
        if not self.poll_task or self.poll_task.done():
            self.poll_task = self.bot.loop.create_task(self._poll())
        suffix = " with TTS" if tts_enabled else ""
        await ctx.send(f"GameWatch started{suffix} for game {number}: {format_update(selected)}")

    def _stop_number(self, number):
        game_id = next((key for key, watch in self.watches.items() if watch["number"] == number), None)
        if game_id is None:
            return False
        del self.watches[game_id]
        if not self.watches:
            self._cancel_poller()
        return True

    def _cancel_poller(self):
        task = self.poll_task
        self.poll_task = None
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if task and not task.done() and task is not current_task:
            task.cancel()

    def _stop_all(self):
        self.watches.clear()
        self._cancel_poller()

    async def _poll(self):
        while self.watches:
            await asyncio.sleep(POLL_SECONDS)
            try:
                games = await self.sports.fetch_gamewatch_games()
                by_id = {game["id"]: game for game in games}
                for game_id, watch in list(self.watches.items()):
                    current = by_id.get(game_id)
                    if not current:
                        LOGGER.warning("Watched game %s missing from scoreboard", game_id)
                        continue
                    if current["sport"] == "MLB":
                        current = await self.sports.enrich_gamewatch_mlb(current)
                    elapsed = time.monotonic() - watch["last_at"]
                    if current["sport"] == "MLB":
                        messages = mlb_updates(watch["last"], current)
                    elif current["sport"] == "NFL":
                        messages = football_updates(watch["last"], current)
                    elif should_announce(watch["last"], current, elapsed):
                        messages = [format_update(current)]
                    else:
                        messages = []
                    for message in messages:
                        await watch["channel"].send(message)
                        if watch["tts"]:
                            await _speak_text_with_voice(message, None)
                    watch["game"] = current
                    if messages:
                        watch["last_at"] = time.monotonic()
                    if messages or current["sport"] in ("MLB", "NFL"):
                        watch["last"] = dict(current)
                    if current.get("completed"):
                        self.watches.pop(game_id, None)
                if not self.watches:
                    self.poll_task = None
                    return
            except asyncio.CancelledError:
                return
            except Exception:
                LOGGER.exception("GameWatch polling failed; will retry")

    def cog_unload(self):
        self._stop_all()


def prepare(bot):
    if not bot.get_cog("GameWatchCog"):
        bot.add_cog(GameWatchCog(bot))
