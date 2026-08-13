from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sqlite3
import time
import uuid
from contextlib import closing
from typing import Awaitable, Callable

from .config import (
    BAITS, BAIT_CATCH_WEIGHTS, BOATS, CHEST_TIERS,
    GUN_CACHE_CHANCE,
    JUNK_CATCHES, LAKE_RECORD_BONUS, MEDAL_MULTIPLIERS, PALETTE,
    PERSONAL_BEST_BONUS, PLAYER_SINK_REPAIR_SECONDS, SPECIES, SPECIES_ALIASES, TIER_CHANCES,
    STEVE_ATTACK_CHANCE, STEVE_JOIN_IMMUNITY_SECONDS,
    STEVE_REPAIR_MAX_SECONDS, STEVE_REPAIR_MIN_SECONDS,
    TREASURE_CHANCE, WEATHER,
)

Broadcaster = Callable[[dict], Awaitable[None]]


class FishingService:
    """The sole authority for rolls and durable fishing state."""

    def __init__(self, db_path: str | None = None, rng: random.Random | None = None):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.db_path = db_path or os.path.join(root, "data", "fishing.db")
        self.rng = rng or random.Random()
        self._lock = asyncio.Lock()
        self._broadcast: Broadcaster | None = None
        self._task: asyncio.Task | None = None
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with closing(self._connect()) as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS anglers (
              user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, opted_in INTEGER NOT NULL DEFAULT 0,
              gold INTEGER NOT NULL DEFAULT 0, fishing_points INTEGER NOT NULL DEFAULT 0, boat_tier INTEGER NOT NULL DEFAULT 1,
              boat_color TEXT NOT NULL, shirt_color TEXT NOT NULL, active_bait TEXT NOT NULL DEFAULT 'worms',
              sink_tokens INTEGER NOT NULL DEFAULT 0, total_catches INTEGER NOT NULL DEFAULT 0,
              steve_strikes INTEGER NOT NULL DEFAULT 0,
              total_weight REAL NOT NULL DEFAULT 0, cooldown_until REAL, cooldown_reason TEXT,
              next_action_at REAL, deployment_until REAL, steve_immune_until REAL,
              last_chat_at REAL, away_since REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS species_stats (
              user_id TEXT NOT NULL REFERENCES anglers(user_id) ON DELETE CASCADE,
              species TEXT NOT NULL, catches INTEGER NOT NULL DEFAULT 0,
              bronze INTEGER NOT NULL DEFAULT 0, silver INTEGER NOT NULL DEFAULT 0,
              gold INTEGER NOT NULL DEFAULT 0, diamond INTEGER NOT NULL DEFAULT 0,
              personal_best REAL, PRIMARY KEY(user_id, species)
            );
            CREATE TABLE IF NOT EXISTS lake_records (
              species TEXT PRIMARY KEY, user_id TEXT NOT NULL, display_name TEXT NOT NULL,
              weight REAL NOT NULL, caught_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fishing_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO fishing_meta(key,value) VALUES('weather','sunny')")
            db.execute("INSERT OR IGNORE INTO fishing_meta(key,value) VALUES('weather_changed_at',?)", (str(time.time()),))
            db.execute("INSERT OR IGNORE INTO fishing_meta(key,value) VALUES('enabled','1')")
            db.execute("INSERT OR IGNORE INTO fishing_meta(key,value) VALUES('steve_last_target','')")
            previous_target = db.execute("SELECT value FROM fishing_meta WHERE key='steve_last_target'").fetchone()
            initial_history = [previous_target["value"]] if previous_target and previous_target["value"] else []
            db.execute(
                "INSERT OR IGNORE INTO fishing_meta(key,value) VALUES('steve_recent_targets',?)",
                (json.dumps(initial_history),),
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(anglers)")}
            if "fishing_points" not in columns:
                db.execute("ALTER TABLE anglers ADD COLUMN fishing_points INTEGER NOT NULL DEFAULT 0")
            if "deployment_until" not in columns:
                db.execute("ALTER TABLE anglers ADD COLUMN deployment_until REAL")
            if "steve_immune_until" not in columns:
                db.execute("ALTER TABLE anglers ADD COLUMN steve_immune_until REAL")
            if "steve_strikes" not in columns:
                db.execute("ALTER TABLE anglers ADD COLUMN steve_strikes INTEGER NOT NULL DEFAULT 0")
            if "last_chat_at" not in columns:
                db.execute("ALTER TABLE anglers ADD COLUMN last_chat_at REAL")
            if "away_since" not in columns:
                db.execute("ALTER TABLE anglers ADD COLUMN away_since REAL")
            migrated = db.execute("SELECT value FROM fishing_meta WHERE key='currency_split_v1'").fetchone()
            if not migrated:
                # Pre-split builds incorrectly stored fish points in gold. Preserve
                # that progress as points and restart treasure-only lifetime gold.
                db.execute("UPDATE anglers SET fishing_points=gold, gold=0, boat_tier=1")
                db.execute("INSERT INTO fishing_meta(key,value) VALUES('currency_split_v1','1')")
            db.commit()

    def set_broadcaster(self, broadcaster: Broadcaster):
        self._broadcast = broadcaster

    async def start(self):
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._run(), name="fishing-simulation")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("[FISHING] Simulation tick failed; retrying")
            await asyncio.sleep(5)

    def _ensure_angler(self, db, user_id: str, display_name: str):
        now = time.time()
        db.execute("""INSERT OR IGNORE INTO anglers
          (user_id,display_name,boat_color,shirt_color,next_action_at,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?)""", (user_id, display_name, self.rng.choice(PALETTE), self.rng.choice(PALETTE), now + self.rng.uniform(12, 30), now, now))
        db.execute("UPDATE anglers SET display_name=?, updated_at=? WHERE user_id=?", (display_name, now, user_id))

    async def set_enabled(self, user_id: str, display_name: str, enabled: bool):
        if enabled and not await self.is_powered_on():
            raise ValueError("MeanGene Lake is currently powered off.")
        async with self._lock:
            with closing(self._connect()) as db:
                self._ensure_angler(db, user_id, display_name)
                now = time.time()
                current = db.execute("SELECT * FROM anglers WHERE user_id=?", (user_id,)).fetchone()
                if enabled and current["cooldown_until"] and current["cooldown_until"] > now:
                    if not current["opted_in"]:
                        db.execute("UPDATE anglers SET opted_in=1,deployment_until=NULL,last_chat_at=?,away_since=NULL,updated_at=? WHERE user_id=?", (now, now, user_id))
                    event = self._event("join_waiting", user_id=user_id, display_name=display_name, cooldown_until=current["cooldown_until"], cooldown_reason=current["cooldown_reason"])
                    snapshot_needed = not current["opted_in"]
                elif enabled and current["opted_in"]:
                    db.execute("UPDATE anglers SET last_chat_at=?,away_since=NULL,updated_at=? WHERE user_id=?", (now, now, user_id))
                    was_away = current["away_since"] is not None
                    event = self._event("angler_joined" if was_away else "already_fishing", user_id=user_id, display_name=display_name)
                    snapshot_needed = was_away
                else:
                    steve_immune_until = now + STEVE_JOIN_IMMUNITY_SECONDS if enabled else None
                    db.execute("UPDATE anglers SET opted_in=?,next_action_at=?,deployment_until=NULL,steve_immune_until=?,last_chat_at=?,away_since=NULL,updated_at=? WHERE user_id=?", (int(enabled), now + self.rng.uniform(8, 20), steve_immune_until, now if enabled else None, now, user_id))
                    event = self._event("angler_joined" if enabled else "angler_left", user_id=user_id, display_name=display_name)
                    snapshot_needed = True
                db.commit()
        if snapshot_needed:
            await self._emit(event, snapshot=True)
        return event

    async def note_chat_activity(self, user_id: str, display_name: str):
        """Update presence and redeploy an enrolled angler returning from AFK."""
        now = time.time()
        event = None
        async with self._lock:
            with closing(self._connect()) as db:
                powered = db.execute("SELECT value FROM fishing_meta WHERE key='enabled'").fetchone()
                if powered and powered["value"] != "1":
                    return None
                row = db.execute("SELECT * FROM anglers WHERE user_id=? AND opted_in=1", (user_id,)).fetchone()
                if not row:
                    return None
                if row["away_since"] is not None:
                    db.execute("UPDATE anglers SET display_name=?,last_chat_at=?,away_since=NULL,next_action_at=?,updated_at=? WHERE user_id=?", (display_name, now, now + self.rng.uniform(8, 18), now, user_id))
                    angler = dict(db.execute("SELECT * FROM anglers WHERE user_id=?", (user_id,)).fetchone())
                    angler["active"] = not angler["cooldown_until"] or angler["cooldown_until"] <= now
                    event = self._event("angler_returned", user_id=user_id, display_name=display_name, angler=angler)
                else:
                    db.execute("UPDATE anglers SET display_name=?,last_chat_at=?,updated_at=? WHERE user_id=?", (display_name, now, now, user_id))
                db.commit()
        if event:
            await self._emit(event, snapshot=False)
        return event

    async def note_viewer_join(self, display_name: str):
        """Redeploy an enrolled angler when Twitch reports them in chat."""
        now = time.time()
        event = None
        async with self._lock:
            with closing(self._connect()) as db:
                row = db.execute(
                    "SELECT * FROM anglers WHERE lower(display_name)=lower(?) AND opted_in=1",
                    (str(display_name or "").lstrip("@"),),
                ).fetchone()
                if row and row["away_since"] is not None:
                    db.execute(
                        "UPDATE anglers SET away_since=NULL,last_chat_at=?,next_action_at=?,updated_at=? WHERE user_id=?",
                        (now, now + self.rng.uniform(8, 18), now, row["user_id"]),
                    )
                    event = self._event(
                        "angler_returned", user_id=row["user_id"], display_name=row["display_name"]
                    )
                    db.commit()
        if event:
            await self._emit(event, snapshot=True)
        return event

    async def note_viewer_part(self, display_name: str):
        """Remove an enrolled boat only when Twitch reports the viewer leaving chat."""
        now = time.time()
        event = None
        async with self._lock:
            with closing(self._connect()) as db:
                row = db.execute(
                    "SELECT * FROM anglers WHERE lower(display_name)=lower(?) AND opted_in=1 AND away_since IS NULL",
                    (str(display_name or "").lstrip("@"),),
                ).fetchone()
                if row:
                    db.execute(
                        "UPDATE anglers SET away_since=?,next_action_at=NULL,updated_at=? WHERE user_id=?",
                        (now, now, row["user_id"]),
                    )
                    event = self._event(
                        "angler_inactive",
                        user_id=row["user_id"],
                        display_name=row["display_name"],
                        reason="left Twitch chat",
                    )
                    db.commit()
        if event:
            await self._emit(event, snapshot=True)
        return event

    async def gps(self, user_id: str):
        if not await self.is_powered_on():
            raise ValueError("MeanGene Lake is currently powered off.")
        async with self._lock:
            with closing(self._connect()) as db:
                row = db.execute("SELECT * FROM anglers WHERE user_id=? AND opted_in=1 AND away_since IS NULL", (user_id,)).fetchone()
        if not row or (row["cooldown_until"] and row["cooldown_until"] > time.time()):
            raise ValueError("Your boat is not currently on the lake.")
        event = self._event("angler_gps", user_id=user_id, display_name=row["display_name"])
        await self._emit(event, snapshot=False)
        return event

    async def is_powered_on(self) -> bool:
        async with self._lock:
            with closing(self._connect()) as db:
                row = db.execute("SELECT value FROM fishing_meta WHERE key='enabled'").fetchone()
                return not row or row["value"] == "1"

    async def set_power(self, enabled: bool):
        async with self._lock:
            with closing(self._connect()) as db:
                db.execute("INSERT OR REPLACE INTO fishing_meta(key,value) VALUES('enabled',?)", ("1" if enabled else "0",))
                if not enabled:
                    db.execute("UPDATE anglers SET opted_in=0,deployment_until=NULL,steve_immune_until=NULL,next_action_at=NULL")
                    db.execute("INSERT OR REPLACE INTO fishing_meta(key,value) VALUES('steve_last_target','')")
                    db.execute("INSERT OR REPLACE INTO fishing_meta(key,value) VALUES('steve_recent_targets','[]')")
                db.commit()
        event = self._event("game_power_changed", enabled=enabled)
        await self._emit(event, snapshot=True)
        return event

    async def set_color(self, user_id: str, display_name: str, field: str, color: str):
        if field not in ("boat_color", "shirt_color") or not self.valid_hex(color):
            raise ValueError("Use a full hex color like #6f42c1.")
        async with self._lock:
            with closing(self._connect()) as db:
                self._ensure_angler(db, user_id, display_name)
                db.execute(f"UPDATE anglers SET {field}=?, updated_at=? WHERE user_id=?", (color.lower(), time.time(), user_id))
                db.commit()
        await self._emit(self._event("appearance_changed", user_id=user_id, display_name=display_name, field=field, color=color.lower()), snapshot=True)

    @staticmethod
    def valid_hex(value: str) -> bool:
        import re
        return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""))

    @staticmethod
    def species_id(value: str) -> str | None:
        return SPECIES_ALIASES.get((value or "").strip().casefold())

    async def set_bait(self, user_id: str, display_name: str, target: str):
        selection = (target or "").strip()
        bait = BAITS[int(selection) - 1] if selection.isdigit() and 1 <= int(selection) <= len(BAITS) else None
        species = bait["target"] if bait else self.species_id(selection)
        bait = bait or next((b for b in BAITS if b["target"] == species), None)
        if not bait:
            raise ValueError("Unknown species target.")
        async with self._lock:
            with closing(self._connect()) as db:
                self._ensure_angler(db, user_id, display_name)
                row = db.execute("SELECT fishing_points FROM anglers WHERE user_id=?", (user_id,)).fetchone()
                if row["fishing_points"] < bait["unlock"]:
                    raise ValueError(f"{bait['label']} unlocks at {bait['unlock']:,} Fishing Points.")
                db.execute("UPDATE anglers SET active_bait=?, updated_at=? WHERE user_id=?", (bait["id"], time.time(), user_id))
                db.commit()
        await self._emit(self._event("bait_changed", user_id=user_id, display_name=display_name, bait=bait["id"]), snapshot=True)
        return bait

    async def move(self, user_id: str):
        if not await self.is_powered_on():
            raise ValueError("MeanGene Lake is currently powered off.")
        async with self._lock:
            with closing(self._connect()) as db:
                row = db.execute("SELECT * FROM anglers WHERE user_id=? AND opted_in=1 AND away_since IS NULL", (user_id,)).fetchone()
                if not row:
                    raise ValueError("Turn fishing on first with !fish on.")
                db.execute("UPDATE anglers SET next_action_at=?, updated_at=? WHERE user_id=?", (time.time() + self.rng.uniform(10, 24), time.time(), user_id))
                db.commit()
        event = self._event("angler_moved", user_id=user_id, display_name=row["display_name"])
        # Movement coordinates are renderer-local and ephemeral. Sending a full
        # snapshot here would immediately reset the destination and cancel the
        # visible transition in both OBS views.
        await self._emit(event, snapshot=False)
        return event

    async def sink(self, attacker_id: str, target_name: str):
        if not await self.is_powered_on():
            raise ValueError("MeanGene Lake is currently powered off.")
        now = time.time()
        async with self._lock:
            with closing(self._connect()) as db:
                attacker = db.execute("SELECT * FROM anglers WHERE user_id=?", (attacker_id,)).fetchone()
                target = db.execute("SELECT * FROM anglers WHERE lower(display_name)=lower(?) AND away_since IS NULL", (target_name.lstrip("@"),)).fetchone()
                if not attacker or attacker["sink_tokens"] < 1:
                    raise ValueError("You do not have a !fish sink token.")
                if not target or not target["opted_in"]:
                    raise ValueError("That angler is not currently fishing.")
                if target["user_id"] == attacker_id:
                    raise ValueError("You cannot sink your own boat.")
                db.execute("UPDATE anglers SET sink_tokens=sink_tokens-1 WHERE user_id=?", (attacker_id,))
                db.execute("UPDATE anglers SET cooldown_until=?, cooldown_reason='player_sink' WHERE user_id=?", (now + PLAYER_SINK_REPAIR_SECONDS, target["user_id"]))
                db.commit()
        event = self._event("boat_sunk", user_id=target["user_id"], display_name=target["display_name"], attacker=attacker["display_name"], cooldown_until=now + PLAYER_SINK_REPAIR_SECONDS, repair_seconds=PLAYER_SINK_REPAIR_SECONDS)
        await self._emit(event, snapshot=True)
        return event

    async def tick(self):
        now = time.time()
        events = []
        async with self._lock:
            with closing(self._connect()) as db:
                powered = db.execute("SELECT value FROM fishing_meta WHERE key='enabled'").fetchone()
                if powered and powered["value"] != "1":
                    return []
                weather, changed = self._weather(db)
                if now - changed >= 90:
                    weather = self.rng.choice(list(WEATHER))
                    db.execute("UPDATE fishing_meta SET value=? WHERE key='weather'", (weather,))
                    db.execute("UPDATE fishing_meta SET value=? WHERE key='weather_changed_at'", (str(now),))
                    events.append(self._event("weather_changed", weather=weather))
                recovered = db.execute("SELECT user_id,display_name FROM anglers WHERE opted_in=1 AND away_since IS NULL AND cooldown_until IS NOT NULL AND cooldown_until<=?", (now,)).fetchall()
                for row in recovered:
                    db.execute("UPDATE anglers SET cooldown_until=NULL,cooldown_reason=NULL,next_action_at=? WHERE user_id=?", (now + self.rng.uniform(8, 18), row["user_id"]))
                    events.append(self._event("angler_redeployed", **dict(row)))
                due = db.execute("SELECT * FROM anglers WHERE opted_in=1 AND away_since IS NULL AND (cooldown_until IS NULL OR cooldown_until<=?) AND next_action_at<=? ORDER BY next_action_at LIMIT 4", (now, now)).fetchall()
                recent_targets_row = db.execute("SELECT value FROM fishing_meta WHERE key='steve_recent_targets'").fetchone()
                try:
                    recent_steve_targets = list(json.loads(recent_targets_row["value"]))[-2:] if recent_targets_row else []
                except (TypeError, ValueError, json.JSONDecodeError):
                    recent_steve_targets = []
                for row in due:
                    steve_eligible = not row["steve_immune_until"] or row["steve_immune_until"] <= now
                    steve_target_allowed = row["user_id"] not in recent_steve_targets
                    if steve_eligible and steve_target_allowed and self.rng.random() < STEVE_ATTACK_CHANCE:
                        until = now + self.rng.uniform(STEVE_REPAIR_MIN_SECONDS, STEVE_REPAIR_MAX_SECONDS)
                        db.execute("UPDATE anglers SET cooldown_until=?,cooldown_reason='steve',next_action_at=?,steve_strikes=steve_strikes+1 WHERE user_id=?", (until, until, row["user_id"]))
                        recent_steve_targets = (recent_steve_targets + [row["user_id"]])[-2:]
                        db.execute("INSERT OR REPLACE INTO fishing_meta(key,value) VALUES('steve_recent_targets',?)", (json.dumps(recent_steve_targets),))
                        events.append(self._event("steve_attack", user_id=row["user_id"], display_name=row["display_name"], cooldown_until=until))
                    else:
                        activity = "cruising" if self.rng.random() < .32 else "casting"
                        events.append(self._event("angler_activity", user_id=row["user_id"], display_name=row["display_name"], activity=activity))
                        if activity == "casting":
                            events.extend(self._roll_catch(db, row, weather))
                        db.execute("UPDATE anglers SET next_action_at=? WHERE user_id=?", (now + self.rng.uniform(12, 25), row["user_id"]))
                db.commit()
        for event in events:
            await self._emit(event, snapshot=event["kind"] not in ("no_catch", "angler_inactive"))
        return events

    async def status(self):
        async with self._lock:
            with closing(self._connect()) as db:
                weather, changed = self._weather(db)
                powered = db.execute("SELECT value FROM fishing_meta WHERE key='enabled'").fetchone()
                enabled = not powered or powered["value"] == "1"
                opted_in = db.execute("SELECT COUNT(*) FROM anglers WHERE opted_in=1").fetchone()[0]
                active = db.execute("SELECT COUNT(*) FROM anglers WHERE opted_in=1 AND away_since IS NULL AND (cooldown_until IS NULL OR cooldown_until<=?)", (time.time(),)).fetchone()[0]
                next_row = db.execute("SELECT MIN(next_action_at) FROM anglers WHERE opted_in=1 AND away_since IS NULL AND (cooldown_until IS NULL OR cooldown_until<=?)", (time.time(),)).fetchone()
                next_at = next_row[0] if next_row else None
        return {"enabled": enabled, "task_running": bool(self._task and not self._task.done()), "weather": weather, "weather_age": max(0, time.time() - changed), "opted_in": opted_in, "active": active, "next_action_in": max(0, next_at - time.time()) if next_at else None}

    def _roll_catch(self, db, angler, weather):
        boat = BOATS[max(0, min(3, angler["boat_tier"] - 1))]
        if self.rng.random() > min(.86, .62 * WEATHER[weather]["bite"] + boat["catch_bonus"]):
            return [self._event("no_catch", user_id=angler["user_id"], display_name=angler["display_name"])]
        events = self._roll_successful_catch(db, angler, weather, second_line=False)
        if angler["boat_tier"] == 4 and self.rng.random() < boat.get("second_line_chance", 0):
            current = db.execute("SELECT * FROM anglers WHERE user_id=?", (angler["user_id"],)).fetchone()
            events.extend(self._roll_successful_catch(db, current, weather, second_line=True))
        return events

    def _roll_successful_catch(self, db, angler, weather, second_line=False):
        bait = next((b for b in BAITS if b["id"] == angler["active_bait"]), BAITS[0])
        fish_weights = BAIT_CATCH_WEIGHTS[bait["id"]]
        choices = list(fish_weights)
        weights = [fish_weights[s] * WEATHER[weather]["species"][s] for s in choices]
        remaining = max(0.0, 100.0 - sum(fish_weights.values()))
        treasure_weight = TREASURE_CHANCE * 100
        cache_weight = GUN_CACHE_CHANCE * 100
        choices.extend(("__treasure__", "__cache__", "__junk__"))
        weights.extend((treasure_weight, cache_weight, max(.01, remaining - treasure_weight - cache_weight)))
        outcome = self.rng.choices(choices, weights=weights, k=1)[0]
        common = {"user_id": angler["user_id"], "display_name": angler["display_name"], "second_line": second_line}
        if outcome == "__treasure__":
            chest = self._weighted_choice(CHEST_TIERS, "chance")
            amount = self.rng.randint(chest["gold_min"], chest["gold_max"])
            old_gold = angler["gold"]
            new_gold = old_gold + amount
            old_tier = angler["boat_tier"]
            new_tier = max(b["tier"] for b in BOATS if new_gold >= b["unlock"])
            db.execute("UPDATE anglers SET gold=?,boat_tier=? WHERE user_id=?", (new_gold, new_tier, angler["user_id"]))
            events = [self._event("treasure", **common, chest_tier=chest["id"], gold=amount, total_gold=new_gold)]
            if new_tier > old_tier:
                events.append(self._event("boat_unlocked", **common, boat_tier=new_tier, boat_name=BOATS[new_tier - 1]["name"]))
            return events
        if outcome == "__cache__":
            db.execute("UPDATE anglers SET sink_tokens=sink_tokens+1 WHERE user_id=?", (angler["user_id"],))
            return [self._event("gun_cache", **common)]
        if outcome == "__junk__":
            return [self._event("junk", **common, item=self.rng.choice(JUNK_CATCHES))]
        species = outcome
        cfg = SPECIES[species]
        tier, weight = self._roll_tier_and_weight(cfg)
        stats = db.execute("SELECT personal_best FROM species_stats WHERE user_id=? AND species=?", (angler["user_id"], species)).fetchone()
        personal_best = not stats or stats["personal_best"] is None or weight > stats["personal_best"]
        db.execute(f"""INSERT INTO species_stats(user_id,species,catches,{tier},personal_best) VALUES(?,?,1,1,?)
          ON CONFLICT(user_id,species) DO UPDATE SET catches=catches+1,{tier}={tier}+1,personal_best=max(COALESCE(personal_best,0),excluded.personal_best)""", (angler["user_id"], species, weight))
        record = db.execute("SELECT weight FROM lake_records WHERE species=?", (species,)).fetchone()
        lake_record = not record or weight > record["weight"]
        if lake_record:
            db.execute("INSERT OR REPLACE INTO lake_records VALUES(?,?,?,?,?)", (species, angler["user_id"], angler["display_name"], weight, time.time()))
        points = round(cfg["points"] * MEDAL_MULTIPLIERS[tier])
        if personal_best:
            points += PERSONAL_BEST_BONUS
        if lake_record:
            points += LAKE_RECORD_BONUS
        old_points = angler["fishing_points"]
        new_points = old_points + points
        target_bait = next(b for b in BAITS if b["target"] == species)
        accidental_locked = old_points < target_bait["unlock"]
        db.execute("UPDATE anglers SET fishing_points=?,total_catches=total_catches+1,total_weight=total_weight+? WHERE user_id=?", (new_points, weight, angler["user_id"]))
        events = [self._event("catch", **common, species=species, species_name=cfg["name"], weight=weight, tier=tier, points=points, total_points=new_points, personal_best=personal_best, lake_record=lake_record, bait=bait["id"], bait_label=bait["label"], accidental_locked=accidental_locked)]
        for unlocked in BAITS:
            if old_points < unlocked["unlock"] <= new_points:
                events.append(self._event("bait_unlocked", **common, bait=unlocked["id"], bait_label=unlocked["label"], species=unlocked["target"], species_name=SPECIES[unlocked["target"]]["name"], threshold=unlocked["unlock"]))
        return events

    def _weighted_choice(self, entries, weight_key):
        return self.rng.choices(entries, weights=[entry[weight_key] for entry in entries], k=1)[0]

    def _roll_tier_and_weight(self, species):
        roll = self.rng.random()
        cumulative = 0.0
        tier = "bronze"
        for candidate, chance in TIER_CHANCES:
            cumulative += chance
            if roll < cumulative:
                tier = candidate
                break
        silver, gold, diamond = species["tiers"]
        ranges = {
            "bronze": (species["min"], silver - 0.1),
            "silver": (silver, gold - 0.1),
            "gold": (gold, diamond - 0.1),
            "diamond": (diamond, species["max"]),
        }
        low, high = ranges[tier]
        return tier, round(self.rng.uniform(low, max(low, high)), 1)

    def _weather(self, db):
        values = dict(db.execute("SELECT key,value FROM fishing_meta WHERE key IN ('weather','weather_changed_at')").fetchall())
        return values.get("weather", "sunny"), float(values.get("weather_changed_at", 0))

    async def snapshot(self):
        async with self._lock:
            with closing(self._connect()) as db:
                weather, _ = self._weather(db)
                now = time.time()
                powered = db.execute("SELECT value FROM fishing_meta WHERE key='enabled'").fetchone()
                enabled = not powered or powered["value"] == "1"
                anglers = [dict(r) for r in db.execute("SELECT * FROM anglers WHERE opted_in=1 AND away_since IS NULL ORDER BY lower(display_name)")] if enabled else []
                for a in anglers:
                    a["active"] = not a["cooldown_until"] or a["cooldown_until"] <= now
                    a["unlocked_baits"] = [b["id"] for b in BAITS if a["fishing_points"] >= b["unlock"]]
                records = [dict(r) for r in db.execute("SELECT * FROM lake_records ORDER BY species")]
        boosted_species = [
            SPECIES[species]["name"]
            for species, multiplier in sorted(WEATHER[weather]["species"].items(), key=lambda item: item[1], reverse=True)
            if multiplier > 1.0
        ]
        return {"type": "fishing_state", "version": 1, "server_time": now, "enabled": enabled, "weather": weather, "weather_boosted_species": boosted_species, "anglers": anglers, "lake_records": records}

    async def angler(self, user_id: str):
        async with self._lock:
            with closing(self._connect()) as db:
                row = db.execute("SELECT * FROM anglers WHERE user_id=?", (user_id,)).fetchone()
                if not row:
                    return None
                result = dict(row)
                result["species"] = [dict(r) for r in db.execute("SELECT * FROM species_stats WHERE user_id=?", (user_id,))]
                return result

    async def angler_by_name(self, display_name: str):
        async with self._lock:
            with closing(self._connect()) as db:
                row = db.execute("SELECT * FROM anglers WHERE lower(display_name)=lower(?)", (display_name.lstrip("@"),)).fetchone()
                if not row:
                    return None
                result = dict(row)
                result["species"] = [dict(r) for r in db.execute("SELECT * FROM species_stats WHERE user_id=?", (row["user_id"],))]
                return result

    async def records(self):
        async with self._lock:
            with closing(self._connect()) as db:
                return [dict(r) for r in db.execute("SELECT * FROM lake_records ORDER BY species")]

    async def ticker_messages(self):
        """Return one random record and one random angler summary per ticker pass."""
        async with self._lock:
            with closing(self._connect()) as db:
                records = db.execute("SELECT * FROM lake_records").fetchall()
                anglers = db.execute("""SELECT a.display_name,a.total_catches,a.fishing_points,a.gold,
                    COALESCE(SUM(s.gold),0) AS gold_medals,
                    COALESCE(SUM(s.diamond),0) AS diamonds
                    FROM anglers a LEFT JOIN species_stats s ON s.user_id=a.user_id
                    WHERE a.total_catches>0 GROUP BY a.user_id""").fetchall()
        messages = []
        if records:
            record = self.rng.choice(records)
            messages.append(f"Fishing Record — {SPECIES[record['species']]['name']}: {record['weight']:.1f} lb by {record['display_name']}")
        if anglers:
            angler = self.rng.choice(anglers)
            messages.append(f"Fishing Stats — {angler['display_name']}: {angler['total_catches']} catches, {angler['fishing_points']:,} pts, {angler['gold_medals']} Gold, {angler['diamonds']} Diamond, {angler['gold']} gold")
        return messages

    @staticmethod
    def _event(kind: str, **payload):
        return {"type": "fishing_event", "version": 1, "event_id": str(uuid.uuid4()), "occurred_at": time.time(), "kind": kind, "payload": payload}

    async def _emit(self, event: dict, snapshot: bool = False):
        if self._broadcast:
            await self._broadcast(event)
            if snapshot:
                await self._broadcast(await self.snapshot())


_service: FishingService | None = None


def get_fishing_service() -> FishingService:
    global _service
    if _service is None:
        _service = FishingService()
    return _service
