"""Compact WoTWoM statistics for insertion immediately before sports."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from bot.wot_api import WotApiClient, WotConfig, load_wot_auth
from bot.wot_operations import operation_stats


_cache: tuple[float, dict[str, Any]] | None = None
_lock = asyncio.Lock()
_rotation_index = 0
CACHE_SECONDS = 900


def build_ticker_messages(
    profile: dict[str, Any], agent_stats: dict[str, Any], rotation_index: int
) -> list[str]:
    private = profile.get("private") or {}
    statistics = profile.get("statistics") or {}
    all_stats = statistics.get("all") or {}
    slots = int(private.get("slots") or 0)
    empty_slots = int(private.get("empty_slots") or 0)
    owned = max(0, slots - empty_slots)
    battles = int(all_stats.get("battles") or 0)
    wins = int(all_stats.get("wins") or 0)
    win_rate = (wins / battles * 100) if battles else 0.0
    trees = int(statistics.get("trees_cut") or 0)
    tank_pool = [
        f"Dar's Garage: {owned:,} vehicles owned",
        f"Dar Tank Record: {battles:,} battles played",
        f"Dar Tank Record: {win_rate:.1f}% win rate",
        f"Dar's Arborist Record: {trees:,} trees knocked over",
    ]
    messages = [tank_pool[rotation_index % len(tank_pool)]]

    if agent_stats.get("total"):
        most_pass = agent_stats.get("most_pass")
        most_fail = agent_stats.get("most_fail")
        if most_pass and most_fail:
            won_text = (
                f"@{most_pass['agent']} ({most_pass['pass']})"
                if most_pass["pass"]
                else "none yet"
            )
            lost_text = (
                f"@{most_fail['agent']} ({most_fail['fail']})"
                if most_fail["fail"]
                else "none yet"
            )
            messages.append(
                "WoTWoM Agents: "
                f"most won challenges {won_text} | "
                f"most lost challenges {lost_text}"
            )
    return messages


async def get_wot_ticker_messages() -> list[str]:
    global _cache, _rotation_index
    async with _lock:
        now = time.monotonic()
        if _cache and now - _cache[0] < CACHE_SECONDS:
            profile = _cache[1]
        else:
            auth = load_wot_auth()
            if not auth.get("access_token") or not auth.get("account_id"):
                return []
            async with aiohttp.ClientSession() as session:
                profile = await WotApiClient(
                    WotConfig.from_env(), session
                ).authenticated_profile(
                    str(auth["access_token"]), str(auth["account_id"])
                )
            _cache = (now, profile)
        messages = build_ticker_messages(
            profile, operation_stats(), _rotation_index
        )
        _rotation_index += 1
        return messages
