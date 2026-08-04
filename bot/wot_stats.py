"""Account-wide World of Tanks Modern Armor statistics for chat commands."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from bot.wot_api import WotApiClient, WotConfig, fetch_wot_inventory


_cache: tuple[float, dict[str, Any]] | None = None
_tank_cache: dict[str, tuple[float, str]] = {}
_player_cache: dict[str, tuple[float, dict[str, str]]] = {}
_player_tank_cache: dict[str, tuple[float, str]] = {}
_cache_lock = asyncio.Lock()
CACHE_SECONDS = 300


class TankLookupError(ValueError):
    pass


def _rate(numerator: int | float, denominator: int | float) -> float:
    return (float(numerator) / float(denominator) * 100) if denominator else 0.0


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else float(numerator)


def _number(value: int | float) -> str:
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}"
    return f"{int(value):,}"


def summarize_stats(
    nickname: str,
    account_statistics: dict[str, Any],
    vehicle_stats: list[dict[str, Any]],
    tank_names: dict[int, str],
) -> dict[str, str]:
    all_stats = account_statistics.get("all") or {}
    battles = int(all_stats.get("battles") or 0)
    wins = int(all_stats.get("wins") or 0)
    survived = int(all_stats.get("survived_battles") or 0)
    deaths = max(0, battles - survived)
    kills = int(all_stats.get("frags") or 0)
    damage = int(all_stats.get("damage_dealt") or 0)
    xp = int(all_stats.get("xp") or 0)
    assisted = sum(
        int(account_statistics.get(field) or 0)
        for field in (
            "damage_assisted_radio",
            "damage_assisted_track",
            "damage_assisted_wheel",
        )
    )

    summary = (
        f"{nickname} | {_number(battles)} battles | "
        f"{_rate(wins, battles):.1f}% wins | "
        f"{_ratio(kills, deaths):.2f} K/D | "
        f"{_number(_ratio(damage, battles))} avg dmg | "
        f"{_number(_ratio(assisted, battles))} avg assisted | "
        f"{_number(_ratio(xp, battles))} avg XP | "
        f"{_rate(survived, battles):.1f}% survival | "
        f"{_number(account_statistics.get('trees_cut') or 0)} trees"
    )

    top_assisted = None
    for row in vehicle_stats:
        vehicle_all = row.get("all") or {}
        total = sum(
            int(vehicle_all.get(field) or 0)
            for field in (
                "damage_assisted_radio",
                "damage_assisted_track",
                "damage_assisted_wheel",
            )
        )
        if top_assisted is None or total > top_assisted[0]:
            top_assisted = (total, int(row["tank_id"]))

    def record(label: str, value_field: str, tank_field: str) -> str:
        value = int(account_statistics.get(value_field) or 0)
        tank_id = int(account_statistics.get(tank_field) or 0)
        return f"{label}: {_number(value)} ({tank_names.get(tank_id, 'unknown tank')})"

    records = " | ".join(
        (
            f"{nickname} records",
            record("damage", "max_damage", "max_damage_tank_id"),
            record("kills", "max_frags", "max_frags_tank_id"),
            record("XP", "max_xp", "max_xp_tank_id"),
            (
                f"assisted career leader: {_number(top_assisted[0])} "
                f"({tank_names.get(top_assisted[1], 'unknown tank')})"
                if top_assisted
                else "assisted career leader: unavailable"
            ),
        )
    )
    return {"summary": summary, "records": records}


def resolve_tank(
    query: str,
    vehicles: list[dict[str, Any]],
    stats_by_id: dict[int, dict[str, Any]] | None = None,
    preferred_mode: str | None = None,
) -> dict[str, Any]:
    requested = query.strip().casefold()
    pool = [
        vehicle
        for vehicle in vehicles
        if not preferred_mode or vehicle.get("mode") == preferred_mode
    ]
    exact = [
        vehicle
        for vehicle in pool
        if str(vehicle["name"]).casefold() == requested
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        stats_by_id = stats_by_id or {}
        return max(
            exact,
            key=lambda vehicle: int(
                (stats_by_id.get(int(vehicle["tank_id"]), {}).get("all") or {}).get(
                    "battles", 0
                )
            ),
        )
    partial = [
        vehicle
        for vehicle in pool
        if requested in str(vehicle["name"]).casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise TankLookupError(f'No tank found matching "{query}".')
    if len({str(vehicle["name"]).casefold() for vehicle in partial}) == 1:
        stats_by_id = stats_by_id or {}
        return max(
            partial,
            key=lambda vehicle: int(
                (stats_by_id.get(int(vehicle["tank_id"]), {}).get("all") or {}).get(
                    "battles", 0
                )
            ),
        )
    names = ", ".join(
        (
            f"{vehicle['name']} "
            f"[{'WWII Tier ' + str(vehicle.get('tier')) if vehicle.get('mode') == 'wwii' else 'Cold War Era ' + str(vehicle.get('era'))}]"
        )
        for vehicle in partial[:5]
    )
    suffix = "…" if len(partial) > 5 else ""
    raise TankLookupError(f"Multiple tanks match: {names}{suffix}")


def summarize_tank(
    vehicle: dict[str, Any], stats: dict[str, Any], nickname: str | None = None
) -> str:
    all_stats = stats.get("all") or {}
    battles = int(all_stats.get("battles") or 0)
    wins = int(all_stats.get("wins") or 0)
    survived = int(all_stats.get("survived_battles") or 0)
    kills = int(all_stats.get("frags") or 0)
    deaths = max(0, battles - survived)
    assisted = sum(
        int(all_stats.get(field) or 0)
        for field in (
            "damage_assisted_radio",
            "damage_assisted_track",
            "damage_assisted_wheel",
        )
    )
    mastery = {
        0: "none",
        1: "3rd Class",
        2: "2nd Class",
        3: "1st Class",
        4: "Ace",
    }.get(int(stats.get("mark_of_mastery") or 0), "unknown")
    label = f"{nickname} — {vehicle['name']}" if nickname else vehicle["name"]
    return (
        f"{label} | {_number(battles)} battles | "
        f"{_rate(wins, battles):.1f}% wins | "
        f"{_ratio(kills, deaths):.2f} K/D | "
        f"{_number(_ratio(int(all_stats.get('damage_dealt') or 0), battles))} avg dmg | "
        f"{_number(_ratio(assisted, battles))} avg assisted | "
        f"{_number(_ratio(int(all_stats.get('xp') or 0), battles))} avg XP | "
        f"{_rate(survived, battles):.1f}% survival | "
        f"{_number(all_stats.get('max_damage') or 0)} max dmg | "
        f"{_number(stats.get('max_frags') or 0)} max kills | mastery: {mastery}"
    )


async def fetch_chat_stats(force: bool = False) -> dict[str, str]:
    global _cache
    async with _cache_lock:
        now = time.monotonic()
        if not force and _cache and now - _cache[0] < CACHE_SECONDS:
            return _cache[1]

        config = WotConfig.from_env()
        async with aiohttp.ClientSession() as session:
            client = WotApiClient(config, session)
            account_id, nickname = await client.resolve_account()
            profile_data, vehicle_data, inventory = await asyncio.gather(
                client._get("account/info/", account_id=account_id),
                client._get("tanks/stats/", account_id=account_id),
                fetch_wot_inventory(),
            )

        profile = (
            profile_data.get(str(account_id))
            if isinstance(profile_data, dict)
            else {}
        ) or {}
        vehicle_stats = (
            vehicle_data.get(str(account_id))
            if isinstance(vehicle_data, dict)
            else []
        ) or []
        tank_names = {
            int(vehicle["tank_id"]): str(vehicle["name"])
            for vehicle in inventory["vehicles"]
        }
        result = summarize_stats(
            nickname or inventory["nickname"],
            profile.get("statistics") or {},
            vehicle_stats,
            tank_names,
        )
        _cache = (now, result)
        return result


async def fetch_tank_chat_stats(query: str, force: bool = False) -> str:
    words = query.strip().split()
    mode_aliases = {
        "wwii": "wwii",
        "ww2": "wwii",
        "cw": "cold_war",
        "coldwar": "cold_war",
        "cold_war": "cold_war",
    }
    preferred_mode = mode_aliases.get(words[0].casefold()) if words else None
    tank_query = " ".join(words[1:] if preferred_mode else words)
    if not tank_query:
        raise TankLookupError("Provide a tank name after the mode.")
    cache_key = f"{preferred_mode or 'auto'}:{tank_query.casefold()}"
    async with _cache_lock:
        now = time.monotonic()
        cached = _tank_cache.get(cache_key)
        if not force and cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]

        config = WotConfig.from_env()
        async with aiohttp.ClientSession() as session:
            client = WotApiClient(config, session)
            account_id, _ = await client.resolve_account()
            vehicle_data, inventory = await asyncio.gather(
                client._get("tanks/stats/", account_id=account_id),
                fetch_wot_inventory(),
            )
        vehicle_stats = (
            vehicle_data.get(str(account_id))
            if isinstance(vehicle_data, dict)
            else []
        ) or []
        stats_by_id = {
            int(row["tank_id"]): row for row in vehicle_stats
        }
        vehicle = resolve_tank(
            tank_query,
            inventory["vehicles"],
            stats_by_id=stats_by_id,
            preferred_mode=preferred_mode,
        )
        stats = stats_by_id.get(int(vehicle["tank_id"]))
        if not stats:
            raise TankLookupError(f"No statistics are available for {vehicle['name']}.")
        result = summarize_tank(vehicle, stats)
        _tank_cache[cache_key] = (now, result)
        return result


async def fetch_player_chat_stats(
    player_name: str, platform: str, force: bool = False
) -> dict[str, str]:
    platform = platform.casefold()
    cache_key = f"{platform}:{player_name.strip().casefold()}"
    async with _cache_lock:
        now = time.monotonic()
        cached = _player_cache.get(cache_key)
        if not force and cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
        config = WotConfig.from_env()
        target = WotConfig(
            application_id=config.application_id,
            player_name=player_name.strip(),
            platform=platform,
            api_root=config.api_root,
        )
        async with aiohttp.ClientSession() as session:
            client = WotApiClient(target, session)
            account_id, nickname = await client.resolve_account()
            profile_data, vehicle_data, inventory = await asyncio.gather(
                client._get("account/info/", account_id=account_id),
                client._get("tanks/stats/", account_id=account_id),
                client.inventory_for_account(account_id, nickname),
            )
        profile = (profile_data.get(str(account_id)) if isinstance(profile_data, dict) else {}) or {}
        vehicle_stats = (vehicle_data.get(str(account_id)) if isinstance(vehicle_data, dict) else []) or []
        tank_names = {int(vehicle["tank_id"]): str(vehicle["name"]) for vehicle in inventory["vehicles"]}
        result = summarize_stats(
            nickname or player_name,
            profile.get("statistics") or {},
            vehicle_stats,
            tank_names,
        )
        _player_cache[cache_key] = (now, result)
        return result


async def fetch_player_tank_chat_stats(
    player_name: str, platform: str, query: str, force: bool = False
) -> str:
    words = query.strip().split()
    mode_aliases = {
        "wwii": "wwii", "ww2": "wwii", "cw": "cold_war",
        "coldwar": "cold_war", "cold_war": "cold_war",
    }
    preferred_mode = mode_aliases.get(words[0].casefold()) if words else None
    tank_query = " ".join(words[1:] if preferred_mode else words)
    if not tank_query:
        raise TankLookupError("Provide a tank name after the player separator.")
    platform = platform.casefold()
    cache_key = (
        f"{platform}:{player_name.strip().casefold()}:"
        f"{preferred_mode or 'auto'}:{tank_query.casefold()}"
    )
    async with _cache_lock:
        now = time.monotonic()
        cached = _player_tank_cache.get(cache_key)
        if not force and cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
        config = WotConfig.from_env()
        target = WotConfig(
            application_id=config.application_id,
            player_name=player_name.strip(),
            platform=platform,
            api_root=config.api_root,
        )
        async with aiohttp.ClientSession() as session:
            client = WotApiClient(target, session)
            account_id, nickname = await client.resolve_account()
            vehicle_data, inventory = await asyncio.gather(
                client._get("tanks/stats/", account_id=account_id),
                client.inventory_for_account(account_id, nickname),
            )
        vehicle_stats = (vehicle_data.get(str(account_id)) if isinstance(vehicle_data, dict) else []) or []
        stats_by_id = {int(row["tank_id"]): row for row in vehicle_stats}
        vehicle = resolve_tank(
            tank_query,
            inventory["vehicles"],
            stats_by_id=stats_by_id,
            preferred_mode=preferred_mode,
        )
        stats = stats_by_id.get(int(vehicle["tank_id"]))
        if not stats:
            raise TankLookupError(f"No statistics are available for {vehicle['name']}.")
        result = summarize_tank(vehicle, stats, nickname or player_name)
        _player_tank_cache[cache_key] = (now, result)
        return result
