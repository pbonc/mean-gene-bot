"""Scheduled WoTWoM inventory refresh and first-battle announcements."""

import asyncio
import logging
import os
import re
import time

from twitchio.ext import commands

from bot.wot_inventory import (
    acknowledge_delivery,
    pending_deliveries,
    record_refresh_error,
    refresh_wot_snapshot,
    snapshot_status,
)
from bot.wot_api import WotApiError
from bot.wot_stats import (
    TankLookupError,
    fetch_chat_stats,
    fetch_player_chat_stats,
    fetch_player_tank_chat_stats,
    fetch_tank_chat_stats,
)
from bot.wot_operations import operation_stats
from bot.wot_sold import (
    acknowledge_sold_announcement,
    pending_sold_announcements,
)


def parse_external_tankstats(content):
    """Parse -x/-p player lookups with either comma or pipe delimiters."""
    match = re.match(r"^\s*!?tankstats\s+(-[xp])\s*,?\s*(.*?)\s*$", content or "", re.I)
    if not match:
        return None
    mode, payload = match.group(1).lower(), match.group(2).strip()
    if "|" in payload:
        player_name, lookup = payload.split("|", 1)
    elif "," in payload:
        player_name, lookup = payload.split(",", 1)
    else:
        player_name, lookup = payload, ""
    return mode, player_name.strip(), lookup.strip()


class WotWomCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.refresh_seconds = max(
            300, int(os.getenv("WOT_INVENTORY_REFRESH_SECONDS", "900"))
        )
        self.task = bot.loop.create_task(self._monitor())
        self.sold_announcement_task = bot.loop.create_task(
            self._sold_announcement_monitor()
        )
        self.last_external_lookup_at = 0.0

    async def _announce_pending(self) -> int:
        channels = list(getattr(self.bot, "connected_channels", None) or [])
        if not channels:
            return 0
        channel = channels[0]
        sent = 0
        for vehicle in pending_deliveries():
            await channel.send(
                f"{vehicle['name']} delivered to the garage, added to inventory."
            )
            await acknowledge_delivery(vehicle["tank_id"])
            sent += 1
        return sent

    async def _refresh(self) -> tuple[int, int]:
        inventory, discovered = await refresh_wot_snapshot()
        announced = await self._announce_pending()
        logging.info(
            "[WOTWOM] Inventory refreshed: %s vehicles, %s new, %s announced",
            len(inventory["vehicles"]),
            len(discovered),
            announced,
        )
        return len(discovered), announced

    async def _monitor(self):
        await asyncio.sleep(10)
        while True:
            try:
                await self._refresh()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.warning("[WOTWOM] Inventory refresh failed: %s", exc)
                await record_refresh_error(str(exc))
            await asyncio.sleep(self.refresh_seconds)

    async def _sold_announcement_monitor(self):
        await asyncio.sleep(5)
        while True:
            try:
                channels = list(
                    getattr(self.bot, "connected_channels", None) or []
                )
                if channels:
                    for item in pending_sold_announcements():
                        await channels[0].send(item["message"])
                        acknowledge_sold_announcement(item["tank_id"])
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.warning(
                    "[WOTWOM] Sold-status announcement failed",
                    exc_info=True,
                )
            await asyncio.sleep(5)

    @commands.command(name="wotgarage")
    async def wotgarage_command(self, ctx):
        is_privileged = bool(
            getattr(ctx.author, "is_mod", False)
            or getattr(ctx.author, "is_broadcaster", False)
        )
        if not is_privileged:
            await ctx.send("Only moderators can manage the WoT garage monitor.")
            return
        parts = (ctx.message.content or "").split()
        if len(parts) > 1 and parts[1].lower() == "refresh":
            try:
                discovered, announced = await self._refresh()
                await ctx.send(
                    f"WoT garage refreshed: {discovered} new, {announced} announced."
                )
            except Exception as exc:
                await ctx.send(f"WoT garage refresh failed: {exc}")
            return
        status = snapshot_status()
        await ctx.send(
            "WoT garage monitor: "
            f"{status['vehicle_count']} vehicles, "
            f"{status['pending_count']} pending, "
            f"last update {status['updated_at'] or 'never'}."
        )

    @commands.command(name="tankstats")
    async def tankstats_command(self, ctx):
        parts = (ctx.message.content or "").split()
        mode = parts[1].lower() if len(parts) > 1 else "summary"
        try:
            external = parse_external_tankstats(ctx.message.content or "")
            if external:
                now = time.monotonic()
                if now - self.last_external_lookup_at < 3:
                    await ctx.send("Player lookup is cooling down; try again in a moment.")
                    return
                mode, player_name, lookup = external
                if not player_name:
                    await ctx.send("Usage: !tankstats -x|-p, <player>, [tank name or records]")
                    return
                self.last_external_lookup_at = now
                platform = mode[1]
                if not lookup:
                    stats = await fetch_player_chat_stats(player_name, platform)
                    await ctx.send(stats["summary"][:480])
                elif lookup.casefold() in {"summary", "records"}:
                    stats = await fetch_player_chat_stats(player_name, platform)
                    await ctx.send(stats[lookup.casefold()][:480])
                elif lookup:
                    await ctx.send(
                        (await fetch_player_tank_chat_stats(player_name, platform, lookup))[:480]
                    )
                else:
                    await ctx.send("Provide records or a tank name after the player name.")
                return
            if mode in {"summary", "records"}:
                stats = await fetch_chat_stats()
                await ctx.send(stats[mode][:480])
                return
            query = " ".join(parts[1:]).strip()
            await ctx.send((await fetch_tank_chat_stats(query))[:480])
        except (TankLookupError, WotApiError) as exc:
            await ctx.send(str(exc)[:480])
        except Exception:
            logging.exception("[WOTWOM] !tankstats failed")
            await ctx.send("World of Tanks statistics are temporarily unavailable.")

    @commands.command(name="opstats")
    async def opstats_command(self, ctx):
        stats = operation_stats()
        if not stats["total"]:
            await ctx.send("No WoTWoM operations have been signed yet.")
            return
        most_pass = stats["most_pass"]
        most_fail = stats["most_fail"]
        won_text = (
            f"@{most_pass['agent']} ({most_pass['pass']} passes)"
            if most_pass["pass"]
            else "none yet"
        )
        fail_text = (
            f"@{most_fail['agent']} ({most_fail['fail']} fails)"
            if most_fail["fail"]
            else "none yet"
        )
        await ctx.send(
            (
                f"WoTWoM operations: {stats['total']} signed | "
                f"most beaten: {won_text} | "
                f"most failures: {fail_text}"
            )[:480]
        )


def prepare(bot):
    bot.add_cog(WotWomCog(bot))
