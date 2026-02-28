# -*- coding: utf-8 -*-
# pyright: reportUndefinedVariable=false
import os
import json
import time
import random
import asyncio
import logging
import importlib
import difflib
import datetime
import types

from twitchio.ext import commands

# Prefer telemetry direct import; fall back to legacy shim if available.
try:
    from bot.telemetry import log_event
except ImportError:  # pragma: no cover - legacy shim path
    from bot.logging_config import log_event  # type: ignore
from bot.overlay_server import broadcast_overlay_message
from bot.telemetry import summarize_rpg_state


def _reset_daily_log_if_needed(self, now_ts: int | None = None):
    """Reset daily log once per calendar day based on UTC date."""
    try:
        ts = now_ts or _now_ts()
        last_reset = self.state.log.get("daily_reset_ts")
        last_date = datetime.utcfromtimestamp(last_reset).date() if last_reset else None
        current_date = datetime.utcfromtimestamp(ts).date()
        if last_date == current_date:
            return
        self.state.log["daily_reset_ts"] = ts
        self.state.log["daily_log"] = []
        self.state.save_log()
    except Exception:
        self.logger.warning("[RPG] _reset_daily_log_if_needed failed", exc_info=True)


def _get_active_revenant_username(self) -> str | None:
    state_obj = self._state_obj()
    if state_obj is None:
        return None
    users = state_obj.state.get("users", {})
    active = [name for name, data in users.items() if self._is_user_revenant(data)]
    if not active:
        return None
    session_active = state_obj.session().get("active_revenant")
    if session_active in active:
        return session_active
    history = state_obj.session().get("revenant_history", [])
    if history:
        last = str(history[-1]).lower()
        if last in active:
            return last
    return active[0]


def _enforce_single_revenant(self):
    state_obj = self._state_obj()
    if state_obj is None:
        return
    users = state_obj.state.get("users", {})
    active = [name for name, data in users.items() if self._is_user_revenant(data)]
    if len(active) <= 1:
        if active:
            self._normalize_revenant_user(active[0], users[active[0]])
        else:
            state_obj.session()["active_revenant"] = None
        return
    keep = self._get_active_revenant_username()
    for name in active:
        if name != keep:
            self._expire_revenant(users[name])
    if keep and keep in users:
        self._normalize_revenant_user(keep, users[keep])
    else:
        state_obj.session()["active_revenant"] = None

def _get_level_from_xp(self, total_xp: int, user_data: dict = None, max_level: int = None) -> int:
    if max_level is None:
        max_level = LEVEL_CAP
    if user_data:
        class_name = user_data.get("class_name", "Derp Clone")
        if user_data.get("is_revenant") or class_name == "Revenant":
            max_level = REVENANT_LEVEL_CAP
        elif class_name == "Streamer":
            max_level = STREAMER_LEVEL_CAP
        elif class_name == "Warlock":
            max_level = WARLOCK_LEVEL_CAP
        elif class_name == "Hop":
            max_level = HOP_LEVEL_CAP
        elif class_name == "Khajiit":
            max_level = KHAJIIT_LEVEL_CAP
        elif class_name == "Archangel":
            max_level = ARCHANGEL_LEVEL_CAP
        elif class_name == "Alchemist":
            max_level = ALCHEMIST_LEVEL_CAP
        elif class_name == "Meatwad":
            max_level = MEATWAD_LEVEL_CAP
        elif class_name == "Deputy":
            max_level = DEPUTY_LEVEL_CAP
        elif class_name == "Buff":
            max_level = BUFF_LEVEL_CAP
        elif class_name == "Barbarian":
            max_level = BARBARIAN_LEVEL_CAP
    for level in range(1, max_level + 1):
        threshold = self._get_xp_needed_for_level(level)
        if total_xp < threshold:
            return level
    return max_level

def _get_xp_at_level(self, total_xp: int, level: int, user_data: dict = None) -> tuple[int, int]:
    max_level = self._get_level_cap(user_data)
    if max_level is None:
        max_level = LEVEL_CAP
    if level >= max_level:
        xp_at_prev_level = self._get_xp_needed_for_level(level - 1) if level > 1 else 0
        return total_xp - xp_at_prev_level, 0
    xp_at_prev_level = self._get_xp_needed_for_level(level - 1) if level > 1 else 0
    xp_needed_for_next = self._get_xp_needed_for_level(level) - xp_at_prev_level
    xp_at_current_level = total_xp - xp_at_prev_level
    return xp_at_current_level, xp_needed_for_next

@commands.command(name="dropship")
async def dropship(self, ctx):
    print("[DEBUG] dropship command triggered")
    self.logger.info("[DEBUG] dropship command triggered by %s", ctx.author.name)
    username = ctx.author.name.lower()
    user = self.state.get_user(username)
    print(f"[DEBUG] dropship user: {username}, class: {user.get('class_name')}")
    if user.get("class_name") != "Streamer":
        print("[DEBUG] dropship: not Streamer class")
        await ctx.send("Only Streamer class can use !dropship.")
        return
    result = self._process_skill(user, "dropship", [], self.state.state)
    print(f"[DEBUG] dropship skill result: {result}")
    self.state.save_state()
    await ctx.send(f"@{username} {result['events'][0]}")

def __init__(self, bot):
    print("[RPG] RpgCog __init__ called")
    self.bot = bot
    self.logger = logging.getLogger("rpg")
    self.logger.info("[RPG] RpgCog __init__ called")
    self.state = RpgState()
    for name in ("_battle_loop_impl", "_queue_monster_action", "_is_user_revenant", "_is_revenant_pass_due"):
        attr = getattr(RpgCog, name, None)
        if attr is None:
            self.logger.warning("[RPG] Helper %s missing on RpgCog during init", name)
            continue
        setattr(self, name, types.MethodType(attr, self))

    self.state._reset_battle_on_startup()
    self._reset_embark_flags_on_startup()
    self._enforce_single_revenant()
    self.state.save_state()
    self._battle_loop_task = self.bot.loop.create_task(self._battle_loop())

def cog_unload(self):
    task = getattr(self, "_battle_loop_task", None)
    if task and not task.done():
        task.cancel()

def _state_obj(self):
    """Return a valid RpgState, rebuilding if state was downgraded to a dict."""
    state_obj = getattr(self, "state", None)
    if hasattr(state_obj, "session"):
        return state_obj
    if isinstance(state_obj, dict):
        try:
            rebuilt = RpgState()
            rebuilt.state = state_obj
            self.state = rebuilt
            return rebuilt
        except Exception:
            self.logger.warning("[RPG] failed to rebuild RpgState from dict", exc_info=True)
            return None
    try:
        self.state = RpgState()
        return self.state
    except Exception:
        self.logger.warning("[RPG] failed to construct RpgState", exc_info=True)
        return None


def session(self) -> dict:
    """Proxy to the underlying RpgState.session for cog instances."""
    state_obj = self._state_obj()
    if state_obj is None:
        return {}
    try:
        return state_obj.session()
    except Exception:
        self.logger.warning("[RPG] session() proxy failed", exc_info=True)
        if hasattr(state_obj, "state"):
            return state_obj.state.setdefault("session", {})
        return {}

async def _battle_loop(self):
    try:
        impl = getattr(type(self), "_battle_loop_impl", None)
        if not impl:
            raise AttributeError("_battle_loop_impl not bound on class")
        await impl(self)
    except AttributeError as exc:
        self.logger.warning("[RPG] Battle loop helper missing; stopping battle loop task.", exc_info=exc)
    except Exception:
        self.logger.exception("[RPG] Battle loop crashed", exc_info=True)

@commands.Cog.event
async def event_command_error(self, ctx, error):
    """Log detailed RPG command errors for easier debugging."""
    cmd_name = getattr(getattr(ctx, "command", None), "name", None)
    if not cmd_name or cmd_name not in getattr(self, "_commands", {}):
        return
    user = getattr(getattr(ctx, "author", None), "name", None)
    msg = getattr(getattr(ctx, "message", None), "content", None)
    self.logger.exception("[RPG] command error cmd=%s user=%s msg=%s", cmd_name, user, msg, exc_info=error)

@commands.command(name="high_stick")
async def high_stick(self, ctx):
    state_obj = self._state_obj()
    if state_obj is None:
        await ctx.send("RPG state unavailable; try !reloadrpg.")
        return
    username = ctx.author.name.lower()
    user = state_obj.get_user(username)
    session = state_obj.session()
    if not session.get("battle_active"):
        await ctx.send("No active battle to join.")
        return
    if session.get("phase") != "action":
        await ctx.send("Action window is closed.")
        return
    participants = session.setdefault("participants", [])
    if username not in participants:
        await ctx.send("You must !join before acting.")
        return
    action_queue = session.get("action_queue", [])
    if any(entry.get("user") == username for entry in action_queue):
        await ctx.send("You already queued an action this turn.")
        return
    result = _enforcer_skill_effect(user, "high_stick", [], self.state.state)
    session.setdefault("action_queue", []).append({"user": username, "action": "high_stick", "damage": 0, "target_index": None, "ts": _now_ts()})
    self.state.save_state()
    self._log_event(f"Queued: @{username} used Enforcer High Stick.", battle=True)
    await ctx.send(f"@{username} uses HIGH STICK! {' '.join(result['events'])}")
    self._broadcast_state()
    await self._resolve_turn_if_ready(session)

@commands.command(name="cross_check")
async def cross_check(self, ctx):
    """Enforcer skill: Cross Check (level 10+)"""
    username = ctx.author.name.lower()
    user = self.state.get_user(username)
    if user.get("class_name") != "Enforcer" or user.get("player_level", 1) < 10:
        await ctx.send("Only Enforcer class at level 10+ can use !cross_check.")
        return
    session = self.state.session()
    if not user.get("active_player"):
        await ctx.send("You must join the battle first.")
        return
    if not session.get("battle_active"):
        await ctx.send("No active battle.")
        return
    if session.get("phase") != "action":
        await ctx.send("Action window is closed.")
        return
    participants = session.setdefault("participants", [])
    if username not in participants:
        await ctx.send("You must !join before acting.")
        return
    action_queue = session.get("action_queue", [])
    if any(entry.get("user") == username for entry in action_queue):
        await ctx.send("You already queued an action this turn.")
        return
    result = _enforcer_skill_effect(user, "cross_check", [], self.state.state)
    session.setdefault("action_queue", []).append({"user": username, "action": "cross_check", "damage": 0, "target_index": None, "ts": _now_ts()})
    self.state.save_state()
    self._log_event(f"Queued: @{username} used Enforcer Cross Check.", battle=True)
    await ctx.send(f"@{username} uses CROSS CHECK! {' '.join(result['events'])}")
    self._broadcast_state()
    await self._resolve_turn_if_ready(session)

@commands.command(name="fight")
async def fight(self, ctx):
    """Enforcer skill: Fight (level 20+)"""
    username = ctx.author.name.lower()
    user = self.state.get_user(username)
    if user.get("class_name") != "Enforcer" or user.get("player_level", 1) < 20:
        await ctx.send("Only Enforcer class at level 20+ can use !fight.")
        return
    session = self.state.session()
    if not user.get("active_player"):
        await ctx.send("You must join the battle first.")
        return
    if not session.get("battle_active"):
        await ctx.send("No active battle.")
        return
    if session.get("phase") != "action":
        await ctx.send("Action window is closed.")
        return
    participants = session.setdefault("participants", [])
    if username not in participants:
        await ctx.send("You must !join before acting.")
        return
    action_queue = session.get("action_queue", [])
    if any(entry.get("user") == username for entry in action_queue):
        await ctx.send("You already queued an action this turn.")
        return
    result = _enforcer_skill_effect(user, "fight", [], self.state.state)
    session.setdefault("action_queue", []).append({"user": username, "action": "fight", "damage": 0, "target_index": None, "ts": _now_ts()})
    self.state.save_state()
    self._log_event(f"Queued: @{username} used Enforcer Fight.", battle=True)
    await ctx.send(f"@{username} uses FIGHT! {' '.join(result['events'])}")
    self._broadcast_state()
    await self._resolve_turn_if_ready(session)

@commands.command(name="slash")
async def slash(self, ctx):
    """Enforcer skill: Slash (level 1+)"""
    username = ctx.author.name.lower()
    user = self.state.get_user(username)
    if user.get("class_name") != "Enforcer":
        await ctx.send("Only Enforcer class can use !slash.")
        return
    session = self.state.session()
    if not user.get("active_player"):
        await ctx.send("You must join the battle first.")
        return
    if not session.get("battle_active"):
        await ctx.send("No active battle.")
        return
    if session.get("phase") != "action":
        await ctx.send("Action window is closed.")
        return
    participants = session.setdefault("participants", [])
    if username not in participants:
        await ctx.send("You must !join before acting.")
        return
    action_queue = session.get("action_queue", [])
    if any(entry.get("user") == username for entry in action_queue):
        await ctx.send("You already queued an action this turn.")
        return
    result = _enforcer_skill_effect(user, "slash", [], self.state.state)
    session.setdefault("action_queue", []).append({"user": username, "action": "slash", "damage": 0, "target_index": None, "ts": _now_ts()})
    self.state.save_state()
    self._log_event(f"Queued: @{username} used Enforcer Slash.", battle=True)
    await ctx.send(f"@{username} uses SLASH! {' '.join(result['events'])}")
    self._broadcast_state()
    await self._resolve_turn_if_ready(session)
REVENANT_CHANCE = 0.02
REVENANT_NEW_GRANTS_ENABLED = False
REVENANT_MAX_BONUS_USES = 3
REVENANT_STREAMS_DURATION = 7
REVENANT_DURATION_DAYS = 7
REVENANT_DURATION_SECONDS = REVENANT_DURATION_DAYS * 24 * 60 * 60
REVENANT_LEVEL_CAP = 1000
REVENANT_KILL_GACHA = 3
REVENANT_KILL_ENTRIES = 1
REAP_AOE_HIT_CHANCE = 0.15
REAP_CRIT_CHANCE = 0.05
REAP_INSTAKILL_CHANCE = 0.005
REAP_BASE_DAMAGE = 30
REAP_DAMAGE_PER_LEVEL = 2
REAP_MAX_BASE_DAMAGE = 250
REVENANT_BASE_HP = 200
REVENANT_HP_PER_LEVEL = 10
REVENANT_UNDEAD_MAX = 3
REVENANT_BLOB_BASE_HP = 180
REVENANT_BLOB_HP_PER_LEVEL = 8
REVENANT_BLOB_DAMAGE = 4
REVENANT_BLOB_MITIGATION = 3
REVENANT_GHOUL_BASE_HP = 150
REVENANT_GHOUL_HP_PER_LEVEL = 10
REVENANT_GHOUL_DAMAGE = 3
REVENANT_GHOUL_DAMAGE_PER_LEVEL = 1
REVENANT_GHOUL_CRIT_CHANCE = 0.25
REVENANT_GHOUL_POISON_DURATION = 3
REVENANT_WISP_BASE_HP = 80
REVENANT_WISP_HP_PER_LEVEL = 6
REVENANT_WISP_HEAL = 3
REVENANT_WISP_PARTY_HEAL = 3
REVENANT_WISP_REZ_COOLDOWN_TURNS = 5
REVENANT_WISP_HEAL_PER_LEVEL = 1
REVENANT_WISP_PARTY_HEAL_LEVEL_STEP = 2
REVENANT_DOOM_COOLDOWN_TURNS = 3
REVENANT_DOOM_BASE_DAMAGE = 10
REVENANT_DOOM_DAMAGE_PER_LEVEL = 1
REVENANT_BERZERK_DAMAGE_MULTIPLIER = 1.25
REVENANT_BERZERK_DURATION_TURNS = 1

MONK_XP_THRESHOLD = 1000000

# Streamer class (special class for iAmDar)
STREAMER_MECH_POOL = [
    {"name": "Locust", "tonnage": 20, "weight": 20, "hp": 60, "armor": 40, "damage": 15, "speed": 100, "special": "evasion", "special_chance": 0.2, "special_effect": "Avoids incoming damage", "attacks_per_turn": 2},
    {"name": "UrbanMech", "tonnage": 30, "weight": 18, "hp": 75, "armor": 60, "damage": 25, "speed": 40, "special": "ac_burst", "special_chance": 0.25, "special_effect": "Double damage", "attacks_per_turn": 1},
    {"name": "Jenner", "tonnage": 35, "weight": 15, "hp": 80, "armor": 55, "damage": 18, "speed": 90, "special": "flank", "special_chance": 1.0, "special_effect": "+10 damage if target damaged", "attacks_per_turn": 2},
    {"name": "Hunchback", "tonnage": 50, "weight": 10, "hp": 120, "armor": 100, "damage": 35, "speed": 50, "special": "ac20", "special_chance": 1.0, "special_effect": "+20 bonus if target HP < 40%", "attacks_per_turn": 1},
    {"name": "Warhammer", "tonnage": 70, "weight": 6, "hp": 140, "armor": 120, "damage": 40, "speed": 45, "special": "dual_ppc", "special_chance": 0.33, "special_effect": "+25 bonus every 3rd attack", "attacks_per_turn": 1},
    {"name": "Timber Wolf", "tonnage": 75, "weight": 5, "hp": 160, "armor": 130, "damage": 45, "speed": 60, "special": "ppc", "special_chance": 1.0, "special_effect": "Ignores 20% armor", "secondary": "missile_barrage", "secondary_chance": 0.2, "secondary_effect": "Hits second random enemy", "attacks_per_turn": 1},
    {"name": "Atlas", "tonnage": 100, "weight": 3, "hp": 220, "armor": 180, "damage": 50, "speed": 30, "special": "intimidate", "special_chance": 1.0, "special_effect": "Enemies deal 10% less damage", "attacks_per_turn": 1},
    {"name": "King Crab", "tonnage": 100, "weight": 3, "hp": 200, "armor": 170, "damage": 60, "speed": 30, "special": "dual_ac20", "special_chance": 0.15, "special_effect": "Fire twice in one turn", "attacks_per_turn": 1},
]
def _streamer_dropship_summon(user, state, rng=random):
    # Only one mech at a time
    if user.get("mech_pet") and user["mech_pet"].get("active", False):
        return {"events": ["Dropship already active: {0}".format(user["mech_pet"]["name"])]}
    # Weighted random selection
    total_weight = sum(m["weight"] for m in STREAMER_MECH_POOL)
    roll = rng.randint(1, total_weight)
    acc = 0
    for mech in STREAMER_MECH_POOL:
        acc += mech["weight"]
        if roll <= acc:
            selected = mech
            break
    else:
        selected = STREAMER_MECH_POOL[-1]
    # Summon mech
    user["mech_pet"] = dict(selected)
    user["mech_pet"]["active"] = True
    user["mech_pet"]["turns_remaining"] = 5  # Mech persists for 5 turns (adjust as needed)
    return {"events": [f"Dropship summoned: {selected['name']} ({selected['tonnage']}t)!"]}
STREAMER_LEVEL_CAP = 100
STREAMER_NAME = "iamdar"
STREAMER_BASE_HP = 40
STREAMER_HP_PER_LEVEL = 10
TOTEM_DAMAGE_BUFF = [1, 5, 0, 0]  # Damage buff effect options (0 = not applicable)
TOTEM_CRIT_CHANCE = 0.30  # 30% chance for auto-crit buff
TOTEM_SHIELD_CHANCE = 0.30  # ~same as autocrit
TOTEM_KILLSHOT_CHANCE = 0.01  # 1% chance for auto-killshot buff
TOTEM_DAMAGE_1_CHANCE = 0.45  # 45% chance for +1 dmg
TOTEM_DAMAGE_5_CHANCE = 0.20  # 20% chance for +5 dmg
TOTEM_HEALING_CHANCE = 0.22  # party-heal totem chance
TOTEM_LABELS = {
    "killshot": "AUTO KILLSHOT",
    "autocrit": "AUTO CRIT",
    "shield": "SHIELD",
    "healing": "PARTY REGEN",
    "damage_5": "+5 DMG",
    "damage_1": "+1 DMG",
    "xp_buff": "XP TOTEM",
}

def _pick_xp_buff():
    # Biased random: 50% chance for 25%, 30% for 50%, 15% for 75%, 5% for 100%
    roll = random.random()
    if roll < 0.5:
        return 25
    elif roll < 0.8:
        return 50
    elif roll < 0.95:
        return 75
    else:
        return 100
STREAMER_TOTEM_MAX_ACTIVE = 4
GAMBA_BASE_DAMAGE = 2
GAMBA_DAMAGE_PER_LEVEL_STEP = 6
GAMBA_BASE_HIT_CHANCE = 0.45
GAMBA_HIT_CHANCE_PER_LEVEL = 0.006
GAMBA_MAX_HIT_CHANCE = 0.70
STREAMER_HEAL_BASE = 4
STREAMER_HEAL_PER_LEVEL_STEP = 4
GAMBA_BASE_BACKFIRE_CHANCE = 0.28
GAMBA_BACKFIRE_REDUCTION_PER_LEVEL = 0.0018
GAMBA_MIN_BACKFIRE_CHANCE = 0.10
GAMBA_SELF_DAMAGE_BASE = 4
GAMBA_SELF_DAMAGE_LEVEL_STEP = 4
GACHA_RARE_CHANCE = 0.15
GACHA_RARE_XP = 100
GACHA_COMMON_XP = 25
GACHA_BONUS_TOKEN_PROC_CHANCE = 0.02
GACHA_ENTRY_BONUS_CHANCE = 0.0025
GACHA_BONUS_TOKEN_DISTRIBUTION = [
    (1, 0.55),
    (2, 0.20),
    (3, 0.10),
    (4, 0.06),
    (5, 0.035),
    (6, 0.02),
    (7, 0.015),
    (8, 0.01),
    (9, 0.007),
    (10, 0.003),
]
STREAMER_PET_SPAWN_POOL = ["timberwolf", "timberwolf", "gordie_howe"]
STREAMER_PET_TIMBERWOLF_HP = 80
STREAMER_PET_GORDIE_HP = 70
STREAMER_PET_TIMBERWOLF_PPC_DAMAGE = 8
STREAMER_PET_TIMBERWOLF_PPC_STUN_CHANCE = 0.35
STREAMER_PET_TIMBERWOLF_LRM_PERCENT = 0.05
STREAMER_PET_GORDIE_GOAL_DAMAGE = 7
STREAMER_PET_GORDIE_FIGHT_PERCENT = 0.10
STREAMER_PET_GORDIE_FIGHT_TARGETS = 3

# Warlock class (special class for fal_the_warlock)
WARLOCK_NAME = "fal_the_warlock"
WARLOCK_LEVEL_CAP = 100
WARLOCK_DOT_DURATION = 3  # DoT lasts 3 turns
WARLOCK_DOT_BASE_DAMAGE = 2  # Base damage per tick
SHADOWBOLT_BASE_DAMAGE = 6
DRAGON_BASE_HP = 200
DRAGON_HP_PER_LEVEL = 5
DRAGON_DOT_CHANCE = 0.25
DRAGON_DOT_DAMAGE = 2
DRAGON_DOT_DURATION = 3
DRAGON_ATTACK_BASE_DAMAGE = 6
DRAGON_ATTACK_DAMAGE_LEVEL_STEP = 3
DRAGON_DOT_DAMAGE_LEVEL_STEP = 6
DRAGON_BITE_CURVE_BONUS_LEVEL_STEP = 8
DRAGON_CLAW_CHANCE = 0.12
DRAGON_CLAW_DAMAGE_MULTIPLIER = 2.5
DRAGON_CLAW_BLEED_DURATION = 3

# Hop class (special class for hoplon5)
HOP_NAME = "hoplon5"
HOP_LEVEL_CAP = 100
HOP_SAP_BASE_CHANCE = 0.25  # 25% base chance to stun with sap
HOP_SAP_CHANCE_PER_LEVEL = 0.02  # +2% per level
HOP_SAP_STUN_DURATION = 1  # Stuns for 1 turn
HOP_DEAGLE_BASE_DAMAGE = 8  # Base damage for deagle
HOP_DEAGLE_HEAVY_CHANCE = 0.30  # 30% chance for heavy damage (2x)
HOP_C4_BASE_DAMAGE = 3  # Base AoE damage
HOP_C4_HIT_CHANCE = 0.60  # 60% chance to hit each target
HOP_GREENARROW_MAX = 6
HOP_GREENARROW_CHANCES = [0.45, 0.25, 0.15, 0.08, 0.05, 0.02]  # 1-6 arrows
HOP_GOLDRPG_PRESET = "normal"  # conservative | normal | aggressive
HOP_GOLDRPG_BASE_DAMAGE_BY_PRESET = {
    "conservative": 7,
    "normal": 8,
    "aggressive": 10,
}
HOP_GOLDRPG_BASE_DAMAGE = HOP_GOLDRPG_BASE_DAMAGE_BY_PRESET.get(HOP_GOLDRPG_PRESET, 8)
HOP_GOLDRPG_BLEED_DURATION = 3

# Khajiit class (special class for caerdwyn)
KHAJIIT_NAME = "caerdwyn"
KHAJIIT_LEVEL_CAP = 100
KHAJIIT_SCRATCH_BASE_DAMAGE = 5  # Moderate damage
KHAJIIT_SCRATCH_BLEED_CHANCE = 0.30  # 30% chance to apply bleed
KHAJIIT_HAIRBALL_BASE_DAMAGE = 4  # Direct damage
KHAJIIT_HAIRBALL_GROSSOUT_CHANCE = 0.35  # 35% chance to apply gross_out
KHAJIIT_MEOW_LIGHT_BASE_DAMAGE = 1
KHAJIIT_MEOW_MODERATE_BASE_DAMAGE = 4
KHAJIIT_MEOW_HEAVY_BASE_DAMAGE = 8
KHAJIIT_GROSSOUT_DAMAGE = 1  # 1 damage per turn
KHAJIIT_GROSSOUT_DURATION = 3  # 3 turns
KHAJIIT_COIN_CHANCES = [0.50, 0.30, 0.15, 0.04, 0.01]  # Chances for 1-5 entries

# Archangel class (special class for karnave)
ARCHANGEL_NAME = "karnave"
ARCHANGEL_LEVEL_CAP = 100
ARCHANGEL_PRAY_POWER_GAIN = 2
ARCHANGEL_PRAY_HEAL = 3  # Base heal amount
ARCHANGEL_TOUCH_POWER_GAIN = 1
ARCHANGEL_TOUCH_BASE_DAMAGE = 3

# Alchemist class (special class for livesuieng)
ALCHEMIST_NAME = "livesuieng"
ALCHEMIST_LEVEL_CAP = 100
ALCHEMIST_BOTTLE_BASE_DAMAGE = 9
ALCHEMIST_BOTTLE_BONUS_CRIT_CHANCE = 0.20
ALCHEMIST_BOTTLE_BLEED_CHANCE = 0.35
ALCHEMIST_BOTTLE_BLEED_DURATION = 2
ALCHEMIST_BOTTLE_SHARD_MAX = 2
ALCHEMIST_BOTTLE_SHARD_DAMAGE = 1
ALCHEMIST_BREW_BUFF_CHANCE = 0.60
ALCHEMIST_BREW_HP_BASE = 4
ALCHEMIST_BREW_DAMAGE_BASE = 2
ALCHEMIST_BREW_CRIT_BASE = 0.08
ALCHEMIST_HUNGOVER_EFFECTIVENESS = 0.90

# Meatwad class (special class for tankadelphia)
MEATWAD_NAME = "tankadelphia"
MEATWAD_ALIASES = {MEATWAD_NAME.lower(), "tankahdelphia"}
MEATWAD_LEVEL_CAP = 100
MEATWAD_BASE_HP = 60
MEATWAD_HP_PER_LEVEL = 6
MEATWAD_CRACK_BERZERK_CHANCE = 0.85
MEATWAD_GUN_BASE_DAMAGE = 7

# Deputy class (special class for deputydawg777)
DEPUTY_NAME = "deputydawg777"
DEPUTY_LEVEL_CAP = 100
DEPUTY_BASE_HP = 60
DEPUTY_HP_PER_LEVEL = 6
DEPUTY_TAZE_BASE_DAMAGE = 6
DEPUTY_TAZE_BASE_STUN_CHANCE = 0.45
DEPUTY_TAZE_STUN_PER_LEVEL = 0.03
DEPUTY_TAZE_MAX_STUN_CHANCE = 0.95
DEPUTY_TEARGASS_COOLDOWN_TURNS = 4
DEPUTY_DONUT_COOLDOWN_TURNS = 5
DEPUTY_TOMMYGUN_COOLDOWN_TURNS = 2
DEPUTY_DONUT_EFFECTIVENESS_MULTIPLIER = 1.10
DEPUTY_DONUT_DURATION_TURNS = 5
DEPUTY_TEARGASS_START_CHANCE = 1.0
DEPUTY_TEARGASS_DECAY = 0.75
DEPUTY_TOMMYGUN_HIT_PERCENT_BASE = 0.08
DEPUTY_TOMMYGUN_HIT_PERCENT_PER_LEVEL = 0.0025
DEPUTY_TOMMYGUN_MIN_HIT_DAMAGE = 3

# Buff class (special class for nate048)
BUFF_NAME = "nate048"
BUFF_LEVEL_CAP = 100
BUFF_BASE_HP = 55
BUFF_HP_PER_LEVEL = 5
BUFF_KID_BASE_HP = 110
BUFF_KID_INTERCEPT_CHANCE = 0.25
BUFF_FRANKLIN_BASE_HP = 35
BUFF_FRANKLIN_BASE_DAMAGE = 2
BUFF_FRANKLIN_CRIT_CHANCE = 0.65
BUFF_FRANKLIN_JDAM_CRIT_CHARGES = 1
BUFF_FRANKLIN_JDAM_CRIT_CHANCE_BONUS = 0.20
BUFF_FRANKLIN_INTERCEPT_CHANCE_BONUS = 0.20
BUFF_JDAM_BASE_DAMAGE = 14
BUFF_NUKE_HP_PERCENT = 0.90
BUFF_NUKE_EXECUTE_CHANCE = 0.25

# Meatwad transformation definitions: (name, rarity_weight, effect_type, effect_value, description, required_level)
# effect_type: "damage", "defense", "heal_self", "heal_party", "regen", "reflect", "lifesteal", "aoe", "dot", "stun_chance", "crit_chance", "evasion", "counter"
MEATWAD_TRANSFORMATIONS = [
    # Level 1: basic attack/tank options
    ("Hammer", 6.0, "party_damage", 2, "Hammer form inspires the party to deal more damage", 1),
    ("Wall", 6.0, "party_defense", 2, "Brick wall grants the party extra defense", 1),
    ("Honey Bear", 5.0, "heal_party", 2, "Sweet honey restores health to all party members each turn", 1),

    # Level 5: one rare unlock
    ("Master Shake", 0.75, "chaos", 0, "Rare chaos form with wild outcomes", 5),

    # One unlock each level after 5
    ("Monster", 1.5, "damage", 8, "Giant form deals devastating damage", 6),
    ("Igloo", 1.5, "defense", 5, "Icy fortress provides massive reduction", 7),
    ("Tornado", 1.5, "aoe", 4, "Whirling winds damage all enemies", 8),
    ("Wesley Snipes", 0.15, "party_super_buff", {
        "damage": 5,
        "crit_chance": 0.25,
        "hp": 20,
        "mitigation": 2,
        "regen": 3,
        "xp": 0.5,
        "auto_kill": True
    }, "Superstar: Massive buffs to all party members and auto-kills 1 random enemy per turn", 9),
    ("Office Building", 1.0, "hp_boost", 30, "Towering structure grants major HP", 10),
]

# Loot Goblin (rare spawn with special rewards)
LOOT_GOBLIN_SPAWN_CHANCE = 0.15  # 15% chance to spawn in any battle
LOOT_GOBLIN_OVERRIDE_CHANCE = 0.35  # If loot goblin spawns, 35% chance to replace the whole wave
LOOT_GOBLIN_HP = 100  # High HP - makes killing blow a lottery/competition
LOOT_GOBLIN_GACHA_REWARD = 2  # Everyone gets 2 gacha tokens
LOOT_GOBLIN_KILLER_GACHA = 2  # Killer gets additional 2 gacha tokens
LOOT_GOBLIN_KILLER_ENTRIES_MIN = 1  # Killer gets 1-5 raffle entries
LOOT_GOBLIN_KILLER_ENTRIES_MAX = 5
LOOT_GOBLIN_REWARD_SCALE_TEAM_EVERY = 20
LOOT_GOBLIN_REWARD_SCALE_KILLER_EVERY = 25
LOOT_GOBLIN_REWARD_SCALE_ENTRIES_EVERY = 30
LOOT_GOBLIN_REWARD_SCALE_BONUS_CAP = 3

# Bestiary
BESTIARY = ["goblin", "squirrel", "trickster", "shaman", "summoner"]
SQUIRREL_NAME = "squirrel"
SQUIRREL_LEVEL = 1
SQUIRREL_HP = 1
SQUIRREL_MAX_PACK = 10
TRICKSTER_NAME = "trickster"
SHAMAN_NAME = "shaman"
SUMMONER_NAME = "summoner"
SKELEMAGE_NAME = "skelemage"
SKELEROG_NAME = "skelerog"
SKELEPRIEST_NAME = "skelepriest"
SKELETANK_NAME = "skeletank"
TRICKSTER_HEX_CHANCE = 0.20
SHAMAN_HEAL_CHANCE = 0.35
SHAMAN_HEAL_BASE = 2
SUMMONER_DOT_DURATION = 3
HEX_FRIENDLY_DAMAGE = 1

# Leveling system
LEVEL_CAP = 10
BASE_CLASS_LEVEL_CAP = 25  # Warrior/Rogue/Mage/Healer
BASE_DAMAGE_BONUS_PER_LEVEL = 1  # Each skill gets +1 damage per level
HP_BONUS_PER_LEVEL = 10  # Standard class progression per level
HEALING_BONUS_PER_LEVEL = 1  # Healers restore +1 HP per level
CRIT_CHANCE_PER_LEVEL = 0.05  # 5% at level 2, 10% at level 3, etc.
CRIT_CHANCE_PER_LEVEL_MAGE_ROGUE = 0.10  # 10% per level for Mage and Rogue (scales faster)
DAMAGE_MITIGATION_PER_LEVEL = 0.75  # Warriors get +0.75 damage mitigation per level
CRIT_MULTIPLIER = 2.0  # Crit does 2x damage
DERP_CLONE_ASCEND_THRESHOLD = 10  # Derp Clone needs 10 damage to ascend

BARBARIAN_LEVEL_CAP = 100
BARBARIAN_BASE_HP = WARRIOR_HP + ((BASE_CLASS_LEVEL_CAP - 1) * HP_BONUS_PER_LEVEL)
BARBARIAN_CLEAVE_BASE_DAMAGE = 29
BARBARIAN_CLEAVE_INDIRECT_MULTIPLIER = 0.5
BARBARIAN_CLEAVE_DIRECT_TARGETS = 3
BARBARIAN_CLEAVE_INDIRECT_TARGETS = 3
BARBARIAN_SHOUT_DAMAGE_MULTIPLIER = 1.10
BARBARIAN_SHOUT_DURATION_TURNS = 3
BARBARIAN_SHOUT_UNLOCK_LEVEL = 5
BARBARIAN_WHIRLWIND_BASE_DAMAGE = 22
BARBARIAN_WHIRLWIND_UNLOCK_LEVEL = 10
BARBARIAN_WHIRLWIND_BLEED_CHANCE = 0.08
BARBARIAN_WHIRLWIND_COOLDOWN_TURNS = 3

CLASS_TIER_SALARIES = {
    0: (1, 1),
    1: (2, 2),
    2: (4, 4),
    3: (6, 6),
}

MYTHIC_SALARY = (25, 25)
SPECIAL_CLASS_SALARY = (5, 5)
SPECIAL_SALARY_CLASSES = {"Meatwad", "Khajiit", "Archangel", "Alchemist"}
REFERRAL_GACHA_TOKENS = 25
REFERRAL_ENTRIES = 25



BASE_CLASSES = ["Warrior", "Rogue", "Mage", "Healer", "Monk", "Enforcer"]

CLASS_MONSTER_SKILLS = {
    "Derp Clone": ("bonk", 1),
    "Warrior": ("strike", 5),
    "Barbarian": ("cleave", BARBARIAN_CLEAVE_BASE_DAMAGE),
    "Rogue": ("backstab", 4),
    "Mage": ("bolt", 6),
    "Healer": ("smite", 4),
    "Monk": ("none", 0),
    "Revenant": ("reap", REAP_BASE_DAMAGE),
    "Warlock": ("corruption", 0),
    "Hop": ("backstab", 4),
    "Khajiit": ("scratch", 5),
    "Archangel": ("pray", 0),
    "Alchemist": ("bottle", ALCHEMIST_BOTTLE_BASE_DAMAGE),
    "Meatwad": ("gun", MEATWAD_GUN_BASE_DAMAGE),
    "Deputy": ("tazer", DEPUTY_TAZE_BASE_DAMAGE),
    "Buff": ("jdam", BUFF_JDAM_BASE_DAMAGE),
}


def _get_enforcer_skills(level):
        # ...existing code...

    # --- Enforcer dictionary assignments (must be after all relevant dicts are defined) ---
    skills = ["slash"]
    if level >= 5:
        skills.append("high_stick")
    if level >= 10:
        skills.append("cross_check")
    if level >= 15:
        skills.append("check")
    if level >= 20:
        skills.append("fight")
    return skills

def _enforcer_skill_effect(user, skill, targets, state, rng=random):
    result = {"events": [], "penalty": False}
    username = user.get("username", "enforcer")
    level = user.get("player_level", 1)
    # Referee penalty check
    def ref_penalty(penalty_type):
        if skill == "fight":
            if rng.random() < ENFORCER_REF_PENALTY_CHANCE:
                result["events"].append(f"Referee spotted {username} fighting! Stunned for 2 minutes.")
                user["stunned_until"] = time.time() + ENFORCER_REF_PENALTY_FIGHT_STUN_SECONDS
                result["penalty"] = True
        else:
            if rng.random() < ENFORCER_REF_PENALTY_CHANCE:
                result["events"].append(f"Referee spotted {username} using {skill}! Stunned for 1 turn.")
                user["stunned_turns"] = ENFORCER_REF_PENALTY_STUN
                result["penalty"] = True

    if skill == "slash":
        dmg = ENFORCER_SLASH_BASE_DAMAGE + (level - 1)
        crit = rng.random() < ENFORCER_SLASH_CRIT_CHANCE
        bleed = rng.random() < ENFORCER_SLASH_BLEED_CHANCE
        if crit:
            dmg = int(dmg * CRIT_MULTIPLIER)
        result["events"].append(f"Slash hits for {dmg}{' (CRIT)' if crit else ''}{' and BLEED' if bleed else ''}!")
        ref_penalty("slash")
    elif skill == "high_stick":
        dmg = ENFORCER_HIGHSTICK_BASE_DAMAGE + (level - 1)
        bleed = rng.random() < ENFORCER_HIGHSTICK_BLEED_CHANCE
        result["events"].append(f"High Stick deals {dmg} and causes heavy BLEED!" if bleed else f"High Stick deals {dmg}.")
        ref_penalty("high_stick")
    elif skill == "cross_check":
        dmg = ENFORCER_CROSSCHECK_BASE_DAMAGE + (level - 1)
        stun = rng.random() < ENFORCER_CROSSCHECK_STUN_CHANCE
        result["events"].append(f"Cross Check smashes for {dmg}{' and STUNS!' if stun else ''}")
        ref_penalty("cross_check")
    elif skill == "fight":
        dmg = ENFORCER_FIGHT_BASE_DAMAGE + (level - 1)
        result["events"].append(f"Fight! {username} deals {dmg} to 5 random enemies!")
        ref_penalty("fight")
    elif skill == "check":
        # Always stun 1, sometimes 2, occasionally 3
        num_targets = 1
        roll = rng.random()
        if roll > 0.85:
            num_targets = 3
        elif roll > 0.5:
            num_targets = 2
        # Crit check
        crit = rng.random() < 0.15  # 15% crit chance (adjust as needed)
        stun_turns = 2 if crit else 1
        # Pick targets (if not provided, pick random enemies)
        session = state.get("session", {})
        monsters = session.get("monsters", [])
        if not monsters:
            result["events"].append("No monsters to stun.")
            return result
        # If targets provided, use them; else pick random
        chosen = []
        if targets:
            for t in targets:
                if isinstance(t, int) and 0 <= t < len(monsters):
                    chosen.append(t)
                if len(chosen) >= num_targets:
                    break
        while len(chosen) < num_targets:
            idx = rng.randint(0, len(monsters)-1)
            if idx not in chosen:
                chosen.append(idx)
        for idx in chosen:
            m = monsters[idx]
            m["stunned_turns"] = stun_turns
        result["events"].append(f"Check stuns {len(chosen)} enemy{'ies' if len(chosen) > 1 else ''} for {stun_turns} turn{'s' if stun_turns > 1 else ''}{' (CRIT)' if crit else ''}!")
        # No penalty for check
    else:
        result["events"].append("Unknown skill.")
    return result

def _get_level_cap(self, user_data: dict = None) -> int:
    if not user_data:
        return LEVEL_CAP
    class_name = user_data.get("class_name", "Derp Clone")
    if class_name == "Enforcer":
        return ENFORCER_LEVEL_CAP
    if user_data.get("is_revenant") or class_name == "Revenant":
        return REVENANT_LEVEL_CAP
    if class_name == "Streamer":
        return STREAMER_LEVEL_CAP
    if class_name == "Warlock":
        return WARLOCK_LEVEL_CAP
    if class_name == "Hop":
        return HOP_LEVEL_CAP
    if class_name == "Khajiit":
        return KHAJIIT_LEVEL_CAP
    if class_name == "Archangel":
        return ARCHANGEL_LEVEL_CAP
    if class_name == "Alchemist":
        return ALCHEMIST_LEVEL_CAP
    if class_name == "Meatwad":
        return MEATWAD_LEVEL_CAP
    if class_name == "Deputy":
        return DEPUTY_LEVEL_CAP
    if class_name == "Buff":
        return BUFF_LEVEL_CAP
    if class_name == "Barbarian":
        return BARBARIAN_LEVEL_CAP
    return LEVEL_CAP
def _calculate_max_hp(self, user: dict) -> int:
    if user.get("class_name") == "Enforcer":
        lvl = user.get("player_level", 1)
        return ENFORCER_BASE_HP + (ENFORCER_HP_PER_LEVEL * (lvl - 1))
    # ...existing code...
# TODO: Remove unused helper (commented out): _get_class_skills
# def _get_class_skills(self, user: dict) -> list:
#     if user.get("class_name") == "Enforcer":
#         return _get_enforcer_skills(user.get("player_level", 1))
#     # ...existing code...
def _process_skill(self, user: dict, skill: str, targets: list, state: dict, rng=random):
    if user.get("class_name") == "Enforcer":
        return _enforcer_skill_effect(user, skill, targets, state, rng)
    if user.get("class_name") == "Streamer" and skill == "dropship":
        return _streamer_dropship_summon(user, state, rng)
    # ...existing code...

CLASS_STREAM_SKILLS = {
    "Warrior": "guard",
    "Rogue": "pickpocket",
    "Mage": "transmute",
    "Healer": "restore",
    "Monk": "blessing",
    "Revenant": "edict/greed",
    "Khajiit": "coin",
    "Meatwad": "none",
    "Deputy": "none",
    "Alchemist": "none",
}

CLASS_MONSTER_SKILLS = {
    "Derp Clone": ("bonk", 1),
    "Warrior": ("strike", 5),
    "Barbarian": ("cleave", BARBARIAN_CLEAVE_BASE_DAMAGE),
    "Rogue": ("backstab", 4),
    "Mage": ("bolt", 6),
    "Healer": ("smite", 4),
    "Monk": ("none", 0),
    "Revenant": ("reap", REAP_BASE_DAMAGE),
    "Warlock": ("corruption", 0),
    "Hop": ("backstab", 4),
    "Khajiit": ("scratch", 5),
    "Archangel": ("pray", 0),
    "Alchemist": ("bottle", ALCHEMIST_BOTTLE_BASE_DAMAGE),
    "Meatwad": ("gun", MEATWAD_GUN_BASE_DAMAGE),
    "Deputy": ("tazer", DEPUTY_TAZE_BASE_DAMAGE),
    "Buff": ("jdam", BUFF_JDAM_BASE_DAMAGE),
}

AUTO_CLASS_ACTIONS = {
    "Derp Clone": [("bonk", 1)],
    "Warrior": [("strike", 5)],
    "Barbarian": [("cleave", BARBARIAN_CLEAVE_BASE_DAMAGE)],
    "Rogue": [("backstab", 4)],
    "Mage": [("bolt", 6)],
    "Healer": [("smite", 4)],
    "Monk": [("ohm", 0)],
    "Enforcer": [("slash", ENFORCER_SLASH_BASE_DAMAGE)],
    "Revenant": [("reap", REAP_BASE_DAMAGE), ("harvest", 10)],
    "Warlock": [("corruption", 0), ("shadowbolt", SHADOWBOLT_BASE_DAMAGE)],
    "Hop": [("deagle", HOP_DEAGLE_BASE_DAMAGE), ("sap", 0), ("backstab", 4)],
    "Khajiit": [("scratch", KHAJIIT_SCRATCH_BASE_DAMAGE), ("hairball", KHAJIIT_HAIRBALL_BASE_DAMAGE)],
    "Archangel": [("pray", 0), ("touch", ARCHANGEL_TOUCH_BASE_DAMAGE)],
    "Alchemist": [("bottle", ALCHEMIST_BOTTLE_BASE_DAMAGE)],
    "Streamer": [("gamba", 0), ("stream_heal", 0)],
    "Meatwad": [("gun", MEATWAD_GUN_BASE_DAMAGE)],
    "Deputy": [("tazer", DEPUTY_TAZE_BASE_DAMAGE)],
    "Buff": [("jdam", BUFF_JDAM_BASE_DAMAGE)],
}


def _utc_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _now_ts():
    return int(time.time())


class RpgState:
    def __init__(self, state_file=STATE_FILE, log_file=LOG_FILE):
        self.logger = logging.getLogger("rpg")
        self.state_file = state_file
        self.log_file = log_file
        self.state = {}
        self.log = {}
        self.load_state()
        self.load_log()

    def load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, "r", encoding="utf-8-sig") as f:
                self.state = json.load(f)
            self.state.setdefault("pending_referrals", [])
        else:
            self.state = {
                "users": {},
                "session": {
                    "stream_id": None,
                    "battle_active": False,
                    "battle_id": None,
                    "monsters": [],
                    "turn_number": 0,
                    "phase": "idle",
                    "action_window_end": None,
                    "join_window_end": None,
                    "participants": [],
                    "action_queue": [],
                    "revenant_history": [],
                    "active_revenant": None,
                    "revenant_class_xp": 0,
                    "spirit_wells": [],
                },
                "pending_referrals": [],
            }
            self.save_state()

    def save_state(self):
        # Synchronize player_level for all users before saving
        users = self.state.get("users", {})
        for username, user in users.items():
            total_xp = int(user.get("xp", 0))
            # Use the same logic as the bot for level calculation
            level = self._get_level_from_xp(total_xp, user)
            user["player_level"] = level
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)
        try:
            payload = summarize_rpg_state(self.state)
            payload["source"] = "rpg_state_save"
            payload["state_file"] = self.state_file
            log_event("rpg_state_snapshot", payload)
        except Exception:
            pass

    def load_log(self):
        if os.path.exists(self.log_file):
            with open(self.log_file, "r", encoding="utf-8-sig") as f:
                self.log = json.load(f)
        else:
            self.log = {
                "daily_reset_ts": None,
                "daily_log": [],
                "battle_log": [],
                "battle_id": None,
            }
            self.save_log()

    def save_log(self):
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(self.log, f, indent=2)
        try:
            payload = summarize_rpg_log(self.log)
            payload["source"] = "rpg_log_save"
            payload["log_file"] = self.log_file
            log_event("rpg_log_snapshot", payload)
        except Exception:
            pass

    def get_user(self, username: str) -> dict:
        username = username.lower()
        # Support being invoked from either RpgState (self.state is a dict) or RpgCog (self.state is RpgState)
        state_container = getattr(self, "state", None)
        state_dict = None
        if hasattr(state_container, "state"):
            state_dict = getattr(state_container, "state", None)
        else:
            state_dict = state_container
        if not isinstance(state_dict, dict):
            state_dict = {}
            if hasattr(state_container, "state"):
                state_container.state = state_dict
            else:
                self.state = state_dict

        users = state_dict.setdefault("users", {})
        if username not in users:
            # Auto-assign special classes to specific users
            if username == STREAMER_NAME.lower():
                class_name = "Streamer"
                class_tier = 1
                base_class = "Streamer"
            elif username == WARLOCK_NAME.lower():
                class_name = "Warlock"
                class_tier = 1
                base_class = "Warlock"
            elif username == HOP_NAME.lower():
                class_name = "Hop"
                class_tier = 1
                base_class = "Hop"
            elif username == KHAJIIT_NAME.lower():
                class_name = "Khajiit"
                class_tier = 1
                base_class = "Khajiit"
            elif username == ARCHANGEL_NAME.lower():
                class_name = "Archangel"
                class_tier = 1
                base_class = "Archangel"
            elif username == ALCHEMIST_NAME.lower():
                class_name = "Alchemist"
                class_tier = 1
                base_class = "Alchemist"
            elif username in MEATWAD_ALIASES:
                class_name = "Meatwad"
                class_tier = 1
                base_class = "Meatwad"
            elif username == DEPUTY_NAME.lower():
                class_name = "Deputy"
                class_tier = 1
                base_class = "Deputy"
            elif username == BUFF_NAME.lower():
                class_name = "Buff"
                class_tier = 1
                base_class = "Buff"
            else:
                class_name = "Derp Clone"
                class_tier = 0
                base_class = "Derp Clone"
            
            users[username] = {
                "class_name": class_name,
                "class_tier": class_tier,
                "base_class": base_class,
                "is_revenant": False,
                "previous_class": None,
                "previous_tier": None,
                "lifetime_monster_damage": 0,
                "active_player": username == STREAMER_NAME.lower(),
                "salary_claimed_this_stream": False,
                "salary_claimed_stream_id": None,
                "daily_embark_ts": None,
                "stream_usage": {},
                "guard_active": False,
                "stolen_from": None,
                "revenant_remaining_uses": 0,
                "revenant_remaining_streams": 0,
                "revenant_bonus_uses_awarded": 0,
                "revenant_acquired_ts": None,
                "xp_before_revenant": None,
                "revenant_xp_at_acquire": None,
                "hp_current": DEFAULT_PLAYER_HP,
                "hp_max": DEFAULT_PLAYER_HP,
                "damage_done": 0,
                "healing_done": 0,
                "monsters_killed": 0,
                "killing_blows": 0,
                "times_knocked_out": 0,
                "xp": 0,
                "player_level": 1,
                "class_change_tokens": 0,
                "referral_awarded": False,
                "referral_referrer": None,
                "referral_bonus_damage": 0,
                "referral_bonus_gacha": 0,
                "hexed_turns_remaining": 0,
                "summoner_dot_damage": 0,
                "summoner_dot_rounds_remaining": 0,
                "archangel_power": 0,
                "hop_goldrpg_ready": False,
                "meatwad_form": None,
                "deputy_teargass_cooldown": 0,
                "deputy_donut_cooldown": 0,
                "deputy_tommygun_cooldown": 0,
                "barbarian_whirlwind_cooldown": 0,
                "revenant_doom_cooldown": 0,
                "next_attack_forced_crit": 0,
                "totem_shield_available": False,
                "alchemist_brew_damage_bonus": 0,
                "alchemist_brew_crit_bonus": 0.0,
                "buff_takeoff_used": False,
                "buff_kid_intercept_triggered": False,
                "buff_franklin_crit_triggered": False,
                "buff_franklin_jdam_buff_triggered": False,
                "buff_jdam_crit_triggered": False,
                "buff_jdam_forced_crit_charges": 0,
            }
        user = users[username]
        
        # Auto-assign special classes to specific users (even if they already exist)
        if username == STREAMER_NAME.lower() and user.get("class_name") != "Streamer":
            user["class_name"] = "Streamer"
            user["class_tier"] = 1
            user["base_class"] = "Streamer"
        if username == STREAMER_NAME.lower():
            user["active_player"] = True
        elif username == WARLOCK_NAME.lower():
            user["base_class"] = "Warlock"
            if user.get("is_revenant"):
                user["previous_class"] = "Warlock"
                if user.get("previous_tier") is None:
                    user["previous_tier"] = 1
            elif user.get("class_name") != "Warlock":
                user["class_name"] = "Warlock"
                user["class_tier"] = 1
        elif username == HOP_NAME.lower() and user.get("class_name") != "Hop":
            user["class_name"] = "Hop"
            user["class_tier"] = 1
            user["base_class"] = "Hop"
        elif username == KHAJIIT_NAME.lower() and user.get("class_name") != "Khajiit":
            user["class_name"] = "Khajiit"
            user["class_tier"] = 1
            user["base_class"] = "Khajiit"
        elif username == ARCHANGEL_NAME.lower() and user.get("class_name") != "Archangel":
            user["class_name"] = "Archangel"
            user["class_tier"] = 1
            user["base_class"] = "Archangel"
        elif username == ALCHEMIST_NAME.lower() and user.get("class_name") != "Alchemist":
            user["class_name"] = "Alchemist"
            user["class_tier"] = 1
            user["base_class"] = "Alchemist"
        elif username in MEATWAD_ALIASES and user.get("class_name") != "Meatwad":
            user["class_name"] = "Meatwad"
            user["class_tier"] = 1
            user["base_class"] = "Meatwad"
        elif username == DEPUTY_NAME.lower() and user.get("class_name") != "Deputy":
            user["class_name"] = "Deputy"
            user["class_tier"] = 1
            user["base_class"] = "Deputy"
        elif username == BUFF_NAME.lower():
            user["base_class"] = "Buff"
            if user.get("is_revenant"):
                user["previous_class"] = "Buff"
                if user.get("previous_tier") is None:
                    user["previous_tier"] = 1
            elif user.get("class_name") != "Buff":
                user["class_name"] = "Buff"
                user["class_tier"] = 1
        
        # Normalize HP values to avoid None/invalid entries breaking overlay payloads
        computed_max_hp = self._calculate_max_hp(user)
        try:
            hp_max_val = int(user.get("hp_max", computed_max_hp) or computed_max_hp)
        except Exception:
            hp_max_val = computed_max_hp
        if hp_max_val <= 0:
            hp_max_val = DEFAULT_PLAYER_HP
        user["hp_max"] = hp_max_val

        try:
            hp_current_val = int(user.get("hp_current", hp_max_val) or hp_max_val)
        except Exception:
            hp_current_val = hp_max_val
        if hp_current_val < 0:
            hp_current_val = 0
        if hp_current_val > hp_max_val:
            hp_current_val = hp_max_val
        user["hp_current"] = hp_current_val
        user.setdefault("damage_done", 0)
        user.setdefault("healing_done", 0)
        user.setdefault("monsters_killed", 0)
        user.setdefault("killing_blows", 0)
        user.setdefault("times_knocked_out", 0)
        user.setdefault("player_level", 1)
        user.setdefault("stolen_from", None)
        user.setdefault("xp", 0)
        user.setdefault("salary_claimed_stream_id", None)
        user.setdefault("xp_before_revenant", None)
        user.setdefault("revenant_xp_at_acquire", None)
        user.setdefault("revenant_acquired_ts", None)
        user.setdefault("class_change_tokens", 0)
        user.setdefault("referral_awarded", False)
        user.setdefault("referral_referrer", None)
        user.setdefault("referral_bonus_damage", 0)
        user.setdefault("referral_bonus_gacha", 0)
        user.setdefault("hexed_turns_remaining", 0)
        user.setdefault("summoner_dot_damage", 0)
        user.setdefault("summoner_dot_rounds_remaining", 0)
        user.setdefault("archangel_power", 0)
        user.setdefault("hop_goldrpg_ready", False)
        user.setdefault("meatwad_form", None)
        user.setdefault("deputy_teargass_cooldown", 0)
        user.setdefault("deputy_donut_cooldown", 0)
        user.setdefault("deputy_tommygun_cooldown", 0)
        user.setdefault("barbarian_whirlwind_cooldown", 0)
        if "revenant_doom_cooldown" not in user:
            user["revenant_doom_cooldown"] = int(user.get("revenant_corruption_cooldown", 0))
        user.setdefault("revenant_doom_cooldown", 0)
        user.setdefault("next_attack_forced_crit", 0)
        user.setdefault("totem_shield_available", False)
        user.setdefault("alchemist_brew_damage_bonus", 0)
        user.setdefault("alchemist_brew_crit_bonus", 0.0)
        user.setdefault("buff_takeoff_used", False)
        user.setdefault("buff_kid_intercept_triggered", False)
        user.setdefault("buff_franklin_crit_triggered", False)
        user.setdefault("buff_franklin_jdam_buff_triggered", False)
        user.setdefault("buff_jdam_crit_triggered", False)
        user.setdefault("buff_jdam_forced_crit_charges", 0)
        return user

    def _calculate_max_hp(self, user: dict) -> int:
        """Calculate max HP based on class, tier, and level."""
        class_name = user.get("class_name", "Derp Clone")
        class_tier = int(user.get("class_tier", 0))
        total_xp = int(user.get("xp", 0))
        level = self._get_level_from_xp(total_xp, user)
        
        # Base HP by class
        if user.get("is_revenant") or class_name == "Revenant":
            base_hp = REVENANT_BASE_HP
        elif class_name == "Streamer":
            base_hp = STREAMER_BASE_HP
        elif class_name == "Meatwad":
            base_hp = MEATWAD_BASE_HP
        elif class_name == "Deputy":
            base_hp = DEPUTY_BASE_HP
        elif class_name == "Buff":
            base_hp = BUFF_BASE_HP
        elif class_name == "Barbarian":
            base_hp = BARBARIAN_BASE_HP
        elif class_name == "Warrior":
            base_hp = WARRIOR_HP  # 25 HP
        elif class_tier > 0:
            base_hp = ASCENDED_PLAYER_HP  # 20 HP for ascended
        else:
            base_hp = DEFAULT_PLAYER_HP  # 10 HP for base/unascended
        
        # Add level-based HP scaling
        if user.get("is_revenant") or class_name == "Revenant":
            if level > 1:
                base_hp += (level - 1) * REVENANT_HP_PER_LEVEL
        elif class_name == "Streamer":
            if level > 1:
                base_hp += (level - 1) * STREAMER_HP_PER_LEVEL
        elif class_name == "Meatwad":
            if level > 1:
                base_hp += (level - 1) * MEATWAD_HP_PER_LEVEL
        elif class_name == "Deputy":
            if level > 1:
                base_hp += (level - 1) * DEPUTY_HP_PER_LEVEL
        elif class_name == "Buff":
            if level > 1:
                base_hp += (level - 1) * BUFF_HP_PER_LEVEL
        elif class_name == "Barbarian":
            if level > 1:
                base_hp += (level - 1) * HP_BONUS_PER_LEVEL
        else:
            # Generic scaling for base/ascended/special classes (e.g., Hop, Rogue, Mage, Healer, Derp, Khajiit, Archangel)
            if level > 1:
                base_hp += (level - 1) * HP_BONUS_PER_LEVEL
        
        return base_hp

    def _get_xp_needed_for_level(self, level: int) -> int:
        """Get cumulative XP threshold to reach a level with scaling growth."""
        linear = level * (level + 1) / 2
        quadratic = level * (level + 1) * (2 * level + 1) / 6
        return int(XP_BASE * (linear + XP_GROWTH_RATE * quadratic))

    def _get_level_from_xp(self, total_xp: int, user_data: dict = None, max_level: int = None) -> int:
        """Determine player level from total XP with class-specific level caps."""
        if max_level is None:
            max_level = LEVEL_CAP
        if user_data:
            class_name = user_data.get("class_name", "Derp Clone")
            if user_data.get("is_revenant") or class_name == "Revenant":
                max_level = REVENANT_LEVEL_CAP
            elif class_name == "Streamer":
                max_level = STREAMER_LEVEL_CAP
            elif class_name == "Warlock":
                max_level = WARLOCK_LEVEL_CAP
            elif class_name == "Hop":
                max_level = HOP_LEVEL_CAP
            elif class_name == "Khajiit":
                max_level = KHAJIIT_LEVEL_CAP
            elif class_name == "Archangel":
                max_level = ARCHANGEL_LEVEL_CAP
            elif class_name == "Alchemist":
                max_level = ALCHEMIST_LEVEL_CAP
            elif class_name == "Meatwad":
                max_level = MEATWAD_LEVEL_CAP
            elif class_name == "Deputy":
                max_level = DEPUTY_LEVEL_CAP
            elif class_name == "Buff":
                max_level = BUFF_LEVEL_CAP
            elif class_name == "Barbarian":
                max_level = BARBARIAN_LEVEL_CAP
        for level in range(1, max_level + 1):
            threshold = self._get_xp_needed_for_level(level)
            if total_xp < threshold:
                return level  # Not enough XP for this level yet
        return max_level  # At or above max level

    def session(self) -> dict:
        session = self.state.setdefault("session", {})
        session.setdefault("stream_id", None)
        session.setdefault("stream_start_ts", None)
        session.setdefault("revenant_history", [])
        session.setdefault("active_revenant", None)
        session.setdefault("revenant_class_xp", 0)
        session.setdefault("undead_pets", [])
        session.setdefault("streamer_pets", [])
        session.setdefault("buff_pets", [])
        session.setdefault("spirit_wells", [])
        session.setdefault("deputy_donut_rounds_remaining", 0)
        session.setdefault("barbarian_shout_rounds_remaining", 0)
        session.setdefault("battle_stat_baseline", {})

        return session

    def _reset_battle_on_startup(self):
        # Keep a state-only version so calling through RpgState never crashes
        session = self.session()
        session["battle_active"] = False
        session["battle_id"] = None
        session["monsters"] = []
        session["turn_number"] = 0
        session["phase"] = "idle"
        session["action_window_end"] = None
        session["join_window_end"] = None
        session["participants"] = []
        session["action_queue"] = []
        session["totems"] = []
        session["imps"] = []
        session["dragons"] = []
        session["green_arrows"] = []
        session["undead_pets"] = []
        session["streamer_pets"] = []
        session["buff_pets"] = []
        session["spirit_wells"] = []
        session["deputy_donut_rounds_remaining"] = 0
        session["barbarian_shout_rounds_remaining"] = 0
        session["battle_stat_baseline"] = {}
        session["slow_actions"] = False
        session["channel"] = None
        self.log.setdefault("battle_log", [])
        self.log["battle_log"] = []
        self.log["battle_id"] = None
        try:
            self.save_state()
            self.save_log()
        except Exception:
            pass

    def _get_or_create_stream_id(self) -> str:
        session = self.session()
        stream_id = session.get("stream_id")
        if stream_id:
            return str(stream_id)
        stream_id = f"stream-{_now_ts()}"
        session["stream_id"] = stream_id
        session["stream_start_ts"] = _now_ts()
        try:
            self.save_state()
        except Exception:
            pass
        return stream_id

    def _start_new_stream_session(self) -> str:
        session = self.session()
        stream_id = f"stream-{_now_ts()}"
        session["stream_id"] = stream_id
        session["stream_start_ts"] = _now_ts()
        session["battle_id"] = None
        session["battle_log"] = [] if "battle_log" in session else session.get("battle_log")
        try:
            self.save_state()
        except Exception:
            pass
        return stream_id

    # Raffle cog lookup is a cog concern; in state context just return None
    def _get_raffle_cog(self):
        return None

    def _build_overlay_payload(self) -> dict:
        session = self.session()
        party = []
        participant_index = 1
        donut_active = int(session.get("deputy_donut_rounds_remaining", 0)) > 0

        for username in session.get("participants", []):
            user = self.get_user(username)
            class_name = user.get("class_name", "Derp Clone")
            if user.get("is_revenant"):
                class_name = "Revenant"

            # Gold glow for Meatwad with Wesley Snipes transformation
            gold_glow = False
            if class_name == "Meatwad":
                form = user.get("meatwad_form")
                if form and form.get("name") == "Wesley Snipes":
                    gold_glow = True

            party.append({
                "number": participant_index,
                "name": username,
                "class": class_name,
                "hp": user.get("hp_current", DEFAULT_PLAYER_HP),
                "hp_max": user.get("hp_max", DEFAULT_PLAYER_HP),
                "goldrpg_ready": bool(user.get("hop_goldrpg_ready")),
                "special_ready": bool(user.get("hop_goldrpg_ready"))
                    or (class_name == "Deputy" and int(user.get("deputy_teargass_cooldown", 0)) <= 0)
                    or (class_name == "Revenant" and int(user.get("revenant_doom_cooldown", 0)) <= 0)
                    or (
                        class_name == "Barbarian"
                        and self._get_level_from_xp(int(user.get("xp", 0)), user) >= BARBARIAN_WHIRLWIND_UNLOCK_LEVEL
                        and int(user.get("barbarian_whirlwind_cooldown", 0)) <= 0
                    )
                    or (
                        class_name == "Buff"
                        and bool(user.get("buff_kid_intercept_triggered"))
                        and bool(user.get("buff_franklin_crit_triggered"))
                        and bool(user.get("buff_jdam_crit_triggered"))
                    ),
                "special_icon": (
                    "\u2622\ufe0f"
                    if (
                        class_name == "Buff"
                        and bool(user.get("buff_kid_intercept_triggered"))
                        and bool(user.get("buff_franklin_crit_triggered"))
                        and bool(user.get("buff_jdam_crit_triggered"))
                    )
                    else None
                ),
                "donut_buff_active": donut_active,
                "is_totem": False,
                "is_imp": False,
                "is_undead": False,
                "gold_glow": gold_glow,
            })
            participant_index += 1

            totems = [t for t in session.get("totems", []) if t.get("owner") == username and t.get("alive")]
            for totem in totems:
                totem_label = self._get_totem_label(totem)
                party.append({
                    "number": None,
                    "name": f"{username}'s Totem",
                    "class": "Totem",
                    "totem_label": totem_label,
                    "hp": totem.get("hp", 1),
                    "hp_max": totem.get("max_hp", 1),
                    "is_totem": True,
                    "is_imp": False,
                    "is_undead": False,
                    "totem_id": totem.get("id"),
                })

            imps = [i for i in session.get("imps", []) if i.get("owner") == username and i.get("alive")]
            for imp in imps:
                party.append({
                    "number": None,
                    "name": f"{username}'s Imp",
                    "class": "Imp",
                    "hp": 1,
                    "hp_max": 1,
                    "is_totem": False,
                    "is_imp": True,
                    "is_undead": False,
                    "is_pet": True,
                    "imp_id": imp.get("id"),
                })

            dragons = [d for d in session.get("dragons", []) if d.get("owner") == username and d.get("alive")]
            for dragon in dragons:
                party.append({
                    "number": None,
                    "name": f"{username}'s Dragon",
                    "class": "Dragon",
                    "hp": dragon.get("hp", 1),
                    "hp_max": dragon.get("max_hp", 1),
                    "is_totem": False,
                    "is_imp": False,
                    "is_undead": False,
                    "is_pet": True,
                    "dragon_id": dragon.get("id"),
                })

            green_arrows = [
                a for a in session.get("green_arrows", [])
                if a.get("owner") == username and a.get("alive")
            ]
            for arrow in green_arrows:
                party.append({
                    "number": None,
                    "name": f"{username}'s Green Arrow",
                    "class": "Green Arrow",
                    "hp": arrow.get("hp", 1),
                    "hp_max": arrow.get("max_hp", 1),
                    "is_totem": False,
                    "is_imp": False,
                    "is_undead": False,
                    "is_pet": True,
                    "green_arrow_id": arrow.get("id"),
                })

            undead_pets = [
                p for p in session.get("undead_pets", [])
                if p.get("owner") == username and p.get("alive")
            ]
            for pet in undead_pets:
                pet_type = str(pet.get("pet_type", "undead")).lower()
                pet_label = {
                    "blob": "Blob",
                    "ghoul": "Ghoul",
                    "wisp": "Wisp",
                }.get(pet_type, "Undead")
                party.append({
                    "number": None,
                    "name": f"{username}'s {pet_label}",
                    "class": pet_label,
                    "hp": pet.get("hp", 1),
                    "hp_max": pet.get("max_hp", 1),
                    "is_totem": False,
                    "is_imp": False,
                    "is_undead": True,
                    "is_pet": True,
                    "undead_id": pet.get("id"),
                })

            streamer_pets = [
                p for p in session.get("streamer_pets", [])
                if p.get("owner") == username and p.get("alive")
            ]
            for pet in streamer_pets:
                pet_type = str(pet.get("pet_type", "streamer_pet")).lower()
                pet_label = {
                    "timberwolf": "Timberwolf",
                    "gordie_howe": "Gordie Howe",
                }.get(pet_type, "Streamer Pet")
                party.append({
                    "number": None,
                    "name": f"{username}'s {pet_label}",
                    "class": pet_label,
                    "hp": pet.get("hp", 1),
                    "hp_max": pet.get("max_hp", 1),
                    "is_totem": False,
                    "is_imp": False,
                    "is_undead": False,
                    "is_pet": True,
                    "streamer_pet_id": pet.get("id"),
                })

            buff_pets = [
                p for p in session.get("buff_pets", [])
                if p.get("owner") == username and p.get("alive")
            ]
            for pet in buff_pets:
                pet_type = str(pet.get("pet_type", "buff_pet")).lower()
                pet_label = {
                    "kid": "Kid",
                    "franklin": "Franklin",
                }.get(pet_type, "Buff Pet")
                party.append({
                    "number": None,
                    "name": f"{username}'s {pet_label}",
                    "class": pet_label,
                    "hp": pet.get("hp", 1),
                    "hp_max": pet.get("max_hp", 1),
                    "is_totem": False,
                    "is_imp": False,
                    "is_undead": False,
                    "is_pet": True,
                    "buff_pet_id": pet.get("id"),
                })

            spirit_wells = [
                w for w in session.get("spirit_wells", [])
                if w.get("owner") == username and w.get("alive")
            ]
            for well in spirit_wells:
                party.append({
                    "number": None,
                    "name": f"{username}'s Spirit Well",
                    "class": "Spirit Well",
                    "hp": well.get("hp", 1),
                    "hp_max": well.get("max_hp", 1),
                    "is_totem": False,
                    "is_imp": False,
                    "is_undead": False,
                    "is_pet": True,
                    "spirit_well_id": well.get("id"),
                })
        
        # Collect usernames who have actions queued this turn
        active_players = [action.get("user") for action in session.get("action_queue", [])]

        # Server-side fallback: if party is empty but participants exist, synthesize basic rows
        if not party and session.get("participants"):
            for idx, username in enumerate(session.get("participants", []), start=1):
                user = self.get_user(username)
                class_name = user.get("class_name", "Derp Clone")
                if user.get("is_revenant"):
                    class_name = "Revenant"
                party.append({
                    "number": idx,
                    "name": username,
                    "class": class_name,
                    "hp": int(user.get("hp_current", 0)),
                    "hp_max": int(user.get("hp_max", DEFAULT_PLAYER_HP)),
                    "goldrpg_ready": bool(user.get("hop_goldrpg_ready")),
                    "special_ready": False,
                    "special_icon": None,
                    "donut_buff_active": donut_active,
                    "is_totem": False,
                    "is_imp": False,
                    "is_undead": False,
                    "gold_glow": False,
                })
        
        log_store = getattr(self, "log", None)
        if log_store is None and hasattr(self, "state"):
            log_store = getattr(self.state, "log", None)

        return {
            "type": "rpg_state",
            "battle_active": bool(session.get("battle_active")),
            "battle_id": session.get("battle_id"),
            "turn_number": session.get("turn_number"),
            "phase": session.get("phase"),
            "action_window_end": session.get("action_window_end"),
            "join_window_end": session.get("join_window_end"),
            "participants": session.get("participants", []),
            "monsters": session.get("monsters", []),
            "party": party,
            "active_players": active_players,
            "daily_log": log_store.get("daily_log", []) if log_store else [],
            "battle_log": log_store.get("battle_log", []) if log_store else [],
        }

    def _resolve_salary(self, user: dict) -> tuple[int, int]:
        """Resolve salary for user. Returns (gacha_tokens, raffle_entries)."""
        if user.get("is_revenant"):
            return MYTHIC_SALARY
        tier = int(user.get("class_tier", 0))
        return CLASS_TIER_SALARIES.get(tier, (1, 1))

    def _get_xp_needed_for_level(self, level: int) -> int:
        """Get cumulative XP threshold to reach a level with scaling growth."""
        linear = level * (level + 1) / 2
        quadratic = level * (level + 1) * (2 * level + 1) / 6
        return int(XP_BASE * (linear + XP_GROWTH_RATE * quadratic))

    def _get_level_cap(self, user_data: dict = None) -> int:
        if not user_data:
            return LEVEL_CAP
        class_name = user_data.get("class_name", "Derp Clone")
        if class_name in {"Warrior", "Rogue", "Mage", "Healer"}:
            return BASE_CLASS_LEVEL_CAP
        if user_data.get("is_revenant") or class_name == "Revenant":
            return REVENANT_LEVEL_CAP
        if class_name == "Streamer":
            return STREAMER_LEVEL_CAP
        if class_name == "Warlock":
            return WARLOCK_LEVEL_CAP
        if class_name == "Hop":
            return HOP_LEVEL_CAP
        if class_name == "Khajiit":
            return KHAJIIT_LEVEL_CAP
        if class_name == "Archangel":
            return ARCHANGEL_LEVEL_CAP
        if class_name == "Alchemist":
            return ALCHEMIST_LEVEL_CAP
        if class_name == "Meatwad":
            return MEATWAD_LEVEL_CAP
        if class_name == "Deputy":
            return DEPUTY_LEVEL_CAP
        if class_name == "Buff":
            return BUFF_LEVEL_CAP
        if class_name == "Barbarian":
            return BARBARIAN_LEVEL_CAP
        return LEVEL_CAP

    def _get_level_from_xp(self, total_xp: int, user_data: dict = None) -> int:
        """Determine player level from total XP with class-specific level caps."""
        # Determine level cap based on class
        max_level = self._get_level_cap(user_data)
        
        for level in range(1, max_level + 1):
            threshold = self._get_xp_needed_for_level(level)
            if total_xp < threshold:
                return level  # Not enough XP for this level yet
        return max_level  # At or above max level

    def _get_xp_at_level(self, total_xp: int, level: int, user_data: dict = None) -> tuple[int, int]:
        """Get XP earned at current level and XP needed to reach next level. Returns (xp_at_level, xp_needed)."""
        max_level = self._get_level_cap(user_data)
        if level >= max_level:
            # At max level, show progress within this level
            xp_at_prev_level = self._get_xp_needed_for_level(level - 1) if level > 1 else 0
            return total_xp - xp_at_prev_level, 0  # 0 needed since maxed
        
        # Get boundaries
        xp_at_prev_level = self._get_xp_needed_for_level(level - 1) if level > 1 else 0
        xp_needed_for_next = self._get_xp_needed_for_level(level) - xp_at_prev_level
        xp_at_current_level = total_xp - xp_at_prev_level
        
        return xp_at_current_level, xp_needed_for_next

    def _get_party_meatwad_form(self, session: dict = None) -> dict | None:
        if not session:
            return None
        participants = session.get("participants", [])
        for username in participants:
            participant = self.state.get_user(username)
            if str(participant.get("class_name", "")).strip().lower() != "meatwad":
                continue
            if int(participant.get("hp_current", 0)) <= 0:
                continue
            form_data = participant.get("meatwad_form")
            if form_data:
                return form_data
        return None

    def _get_effective_meatwad_form(self, user_data: dict = None, session: dict = None) -> dict | None:
        party_form = self._get_party_meatwad_form(session)
        if party_form:
            return party_form
        if user_data:
            return user_data.get("meatwad_form")
        return None

    def _get_crit_chance(self, user_data: dict, level: int, session: dict = None) -> float:
        """Get total crit chance: base 10% + level scaling (varies by class)."""
        class_name = user_data.get("class_name", "Derp Clone")
        
        # All classes start with 10% base crit
        crit_chance = BASE_CRIT_CHANCE
        
        # Tier 1 classes also get level-based scaling
        if level >= 2:
            if class_name in ["Mage", "Rogue"]:
                # Mage and Rogue get faster crit scaling: +10% per level
                crit_chance += (level - 1) * CRIT_CHANCE_PER_LEVEL_MAGE_ROGUE
            else:
                # Other classes get standard scaling: +5% per level
                crit_chance += (level - 1) * CRIT_CHANCE_PER_LEVEL
        
        # Add Meatwad transformation crit bonuses
        form_data = self._get_effective_meatwad_form(user_data, session)
        if form_data and form_data.get("effect_type") == "crit_chance":
            crit_chance += float(form_data.get("effect_value", 0))
        
        return min(crit_chance, 1.0)  # Cap at 100%

    def _calculate_damage_with_scaling(self, base_damage: int, user_data: dict, session: dict = None, include_crit_meta: bool = False):
        """Calculate damage with level-based bonuses, crit chance, and monk blessing bonus."""
        class_name = user_data.get("class_name", "Derp Clone")
        referral_bonus = int(user_data.get("referral_bonus_damage", 0))
        alchemist_brew_bonus = int(user_data.get("alchemist_brew_damage_bonus", 0))
        totem_damage_bonus = 0
        effectiveness_multiplier = self._get_donut_effectiveness_multiplier(session)
        if session:
            totem_buff = self._get_totem_buff(session)
            totem_damage_bonus = int(totem_buff.get("damage_bonus", 0))
        
        # Skip damage scaling for Monk and Revenant
        if class_name == "Monk" or user_data.get("is_revenant"):
            result = int((base_damage + referral_bonus + totem_damage_bonus + alchemist_brew_bonus) * effectiveness_multiplier)
            return (result, False) if include_crit_meta else result
        
        # Derp Clone stays at base damage
        if class_name == "Derp Clone":
            result = int((base_damage + referral_bonus + totem_damage_bonus + alchemist_brew_bonus) * effectiveness_multiplier)
            return (result, False) if include_crit_meta else result
        
        # Tier 1 classes get level bonuses and crit
        total_xp = int(user_data.get("xp", 0))
        level = self._get_level_from_xp(total_xp, user_data)
        level_bonus = (level - 1) * BASE_DAMAGE_BONUS_PER_LEVEL
        crit_chance = self._get_crit_chance(user_data, level, session)
        crit_chance += float(user_data.get("alchemist_brew_crit_bonus", 0.0))
        crit_chance = min(1.0, crit_chance)
        
        # Apply crit to base damage only, then add level bonus
        final_damage = base_damage
        did_crit = False
        if self._consume_forced_crit(user_data):
            final_damage = int(final_damage * CRIT_MULTIPLIER)
            did_crit = True
        elif random.random() < crit_chance:
            final_damage = int(final_damage * CRIT_MULTIPLIER)
            did_crit = True
        
        final_damage = final_damage + level_bonus + alchemist_brew_bonus
        
        # Apply monk blessing bonus: 50% per monk in the party (additive)
        if session:
            participants = session.get("participants", [])
            monk_count = sum(1 for participant in participants if self.state.get_user(participant).get("class_name") == "Monk")
            if monk_count > 0:
                monk_bonus = 0.5 * monk_count
                final_damage = int(final_damage * (1 + monk_bonus))
            final_damage += totem_damage_bonus
        
        # Apply Meatwad transformation damage bonuses
        form_data = self._get_effective_meatwad_form(user_data, session)
        if form_data:
            effect_type = form_data.get("effect_type", "")
            effect_value = form_data.get("effect_value", 0)
            
            if effect_type == "damage":
                # Direct damage bonus (Monster, Lincoln, Hammer, Humanoid, Slim Jim)
                final_damage += int(effect_value)
            elif effect_type == "party_damage":
                # Party synergy damage (Bridge 2.0, Famous Phrase)
                if session:
                    alive_count = len(self._get_alive_participants(session))
                    final_damage += int(effect_value * alive_count)
            elif effect_type == "balanced":
                # Balanced bonus (Humanoid 3) - damage + defense
                final_damage += int(effect_value)
            elif effect_type == "five_boost":
                # Number 5 form - 5% boost to everything
                final_damage = int(final_damage * (1 + effect_value))
            elif effect_type == "chaos":
                # Master Shake form - random chaos effect
                chaos_roll = random.random()
                if chaos_roll < 0.25:
                    final_damage = int(final_damage * 2)  # Double damage
                elif chaos_roll < 0.50:
                    final_damage = int(final_damage * 0.5)  # Half damage
                elif chaos_roll < 0.60:
                    final_damage = 0  # Miss completely
        
        result = int((final_damage + referral_bonus) * effectiveness_multiplier)
        return (result, did_crit) if include_crit_meta else result

    def _clear_alchemist_brew_bonuses(self, usernames: list[str] = None):
        helper = getattr(self, "_state_obj", None)
        state_obj = helper() if callable(helper) else None
        if state_obj is None and isinstance(self, RpgState):
            state_obj = self
        if state_obj is None:
            self.logger.warning("[RPG] _clear_alchemist_brew_bonuses: state unavailable")
            return
        users = state_obj.state.get("users", {})
        if usernames is None:
            targets = users.values()
        else:
            targets = [users.get(name) for name in usernames if name in users]
        for user_data in targets:
            if not user_data:
                continue
            user_data["alchemist_brew_damage_bonus"] = 0
            user_data["alchemist_brew_crit_bonus"] = 0.0

    def _consume_forced_crit(self, user_data: dict) -> bool:
        charges = int(user_data.get("next_attack_forced_crit", 0))
        if charges <= 0:
            return False
        user_data["next_attack_forced_crit"] = charges - 1
        return True

    # TODO: Remove unused helper (commented out): _build_streamer_pet
    # def _build_streamer_pet(self, owner: str, pet_type: str) -> dict:
    #     normalized = str(pet_type or "").strip().lower()
    #     pet_id = f"streamer_pet_{normalized}_{owner}_{_now_ts()}"
    #     if normalized == "timberwolf":
    #         return {
    #             "id": pet_id,
    #             "owner": owner,
    #             "alive": True,
    #             "pet_type": "timberwolf",
    #             "hp": STREAMER_PET_TIMBERWOLF_HP,
    #             "max_hp": STREAMER_PET_TIMBERWOLF_HP,
    #             "ppc_damage": STREAMER_PET_TIMBERWOLF_PPC_DAMAGE,
    #             "ppc_stun_chance": STREAMER_PET_TIMBERWOLF_PPC_STUN_CHANCE,
    #             "lrm_percent": STREAMER_PET_TIMBERWOLF_LRM_PERCENT,
    #         }
    #     return {
    #         "id": pet_id,
    #         "owner": owner,
    #         "alive": True,
    #         "pet_type": "gordie_howe",
    #         "hp": STREAMER_PET_GORDIE_HP,
    #         "max_hp": STREAMER_PET_GORDIE_HP,
    #         "goal_damage": STREAMER_PET_GORDIE_GOAL_DAMAGE,
    #         "fight_percent": STREAMER_PET_GORDIE_FIGHT_PERCENT,
    #     }

    def _add_pet_owner_damage(self, owner: str, dealt: int):
        owner_key = str(owner or "").strip().lower()
        if dealt <= 0 or not owner_key or owner_key == "?":
            return
        owner_data = self.state.get_user(owner_key)
        owner_data["lifetime_monster_damage"] = int(owner_data.get("lifetime_monster_damage", 0)) + int(dealt)
        owner_data["damage_done"] = int(owner_data.get("damage_done", 0)) + int(dealt)

    def _despawn_buff_pets_for_owner(self, session: dict, owner: str) -> list[str]:
        owner_key = str(owner or "").strip().lower()
        if not owner_key:
            return []
        removed: list[str] = []
        for pet in session.get("buff_pets", []):
            if not pet.get("alive"):
                continue
            if str(pet.get("owner", "")).strip().lower() != owner_key:
                continue
            pet_type = str(pet.get("pet_type", "")).strip().lower()
            pet["alive"] = False
            if pet_type == "kid":
                removed.append("Kid")
            elif pet_type == "franklin":
                removed.append("Franklin")
            else:
                removed.append("Buff Pet")
        return removed

    async def _trigger_archangel_death_passive(self, session: dict, username: str) -> bool:
        user = self.state.get_user(username)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "archangel" and username != ARCHANGEL_NAME.lower():
            return False

        user["times_knocked_out"] = int(user.get("times_knocked_out", 0)) + 1
        level = self._get_level_from_xp(int(user.get("xp", 0)), user)
        power = int(user.get("archangel_power", 0))

        burst_damage = int((power * 4) + ((level * power) / 4))
        total_dealt = 0
        defeated = 0
        if burst_damage > 0:
            alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
            for monster in alive_monsters:
                hp_before = int(monster.get("hp", 0))
                dealt = min(burst_damage, hp_before)
                monster["hp"] = max(0, hp_before - burst_damage)
                total_dealt += dealt
                if monster.get("hp", 0) <= 0 and monster.get("alive"):
                    monster["alive"] = False
                    monster["killed_by"] = username
                    user["monsters_killed"] = int(user.get("monsters_killed", 0)) + 1
                    user["killing_blows"] = int(user.get("killing_blows", 0)) + 1
                    defeated += 1
                    if monster.get("is_loot_goblin"):
                        await self._award_loot_goblin_rewards(
                            session,
                            username,
                            int(monster.get("level", 1)),
                        )
            user["lifetime_monster_damage"] = int(user.get("lifetime_monster_damage", 0)) + total_dealt
            user["damage_done"] = int(user.get("damage_done", 0)) + total_dealt

        user["archangel_power"] = 0

        spirit_wells = [
            w for w in session.get("spirit_wells", [])
            if w.get("alive") and w.get("owner") != username
        ]
        max_hp = max(1, level * 5)
        spirit_wells.append({
            "id": f"spirit_well_{username}_{_now_ts()}",
            "owner": username,
            "alive": True,
            "level": level,
            "hp": min(5, max_hp),
            "max_hp": max_hp,
        })
        session["spirit_wells"] = spirit_wells

        self._log_event(
            f"Archangel fall: @{username} released {total_dealt} deathburst damage and formed a Spirit Well.",
            battle=True,
        )
        await self._send_battle_message(
            f"ðŸ•Šï¸ @{username} falls! Deathburst deals {total_dealt} total damage and a Spirit Well appears (5/{max_hp} HP)."
        )
        if defeated > 0:
            await self._send_battle_message(
                f"@{username}'s deathburst defeated {defeated} enemy(ies)!"
            )
        return True

    async def _process_archangel_spirit_wells(self, session: dict):
        spirit_wells = [w for w in session.get("spirit_wells", []) if w.get("alive")]
        if not spirit_wells:
            session["spirit_wells"] = []
            return

        for well in spirit_wells:
            owner = str(well.get("owner", "")).strip().lower()
            if not owner:
                well["alive"] = False
                continue

            owner_data = self.state.get_user(owner)
            owner_hp = int(owner_data.get("hp_current", 0))
            if owner_hp > 0:
                well["alive"] = False
                continue

            level = max(1, int(well.get("level", 1)))
            max_hp = max(1, int(well.get("max_hp", level * 5)))
            hp_now = max(0, int(well.get("hp", 0)))

            self_heal = min(level, max_hp - hp_now)
            if self_heal > 0:
                well["hp"] = hp_now + self_heal
                hp_now = int(well.get("hp", hp_now))

            ally_candidates = [
                name for name in session.get("participants", [])
                if name != owner and int(self.state.get_user(name).get("hp_current", 0)) > 0
            ]
            if ally_candidates:
                ally_name = random.choice(ally_candidates)
                ally_data = self.state.get_user(ally_name)
                ally_hp = int(ally_data.get("hp_current", 0))
                ally_max = int(ally_data.get("hp_max", DEFAULT_PLAYER_HP))
                ally_heal = min(level, max(0, ally_max - ally_hp))
                if ally_heal > 0:
                    ally_data["hp_current"] = ally_hp + ally_heal
                    owner_data["healing_done"] = int(owner_data.get("healing_done", 0)) + ally_heal
                    await self._send_battle_message(
                        f"ðŸ’§ @{owner}'s Spirit Well heals @{ally_name} for {ally_heal}."
                    )

            if hp_now >= max_hp:
                owner_data["hp_current"] = int(owner_data.get("hp_max", DEFAULT_PLAYER_HP))
                well["alive"] = False
                self._log_event(
                    f"Spirit Well: @{owner} was revived at full health.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"âœ¨ @{owner}'s Spirit Well is full and revives them at full health!"
                )
            else:
                await self._send_battle_message(
                    f"ðŸ’§ @{owner}'s Spirit Well restores itself for {self_heal} (HP {hp_now}/{max_hp})."
                )

        session["spirit_wells"] = [w for w in spirit_wells if w.get("alive")]

    def _get_dragon_combat_stats(self, owner: str) -> tuple[int, int, int]:
        owner_name = str(owner or "").strip().lower()
        owner_data = self.state.get_user(owner_name) if owner_name else {}
        warlock_level = self._get_level_from_xp(int(owner_data.get("xp", 0)), owner_data)

        bite_damage = DRAGON_ATTACK_BASE_DAMAGE + ((warlock_level - 1) // DRAGON_ATTACK_DAMAGE_LEVEL_STEP)
        bite_damage += (warlock_level - 1) // DRAGON_BITE_CURVE_BONUS_LEVEL_STEP
        bite_damage = max(1, bite_damage)

        dot_damage = DRAGON_DOT_DAMAGE + ((warlock_level - 1) // DRAGON_DOT_DAMAGE_LEVEL_STEP)
        dot_damage = max(1, dot_damage)

        claw_damage = max(bite_damage + 2, int(bite_damage * DRAGON_CLAW_DAMAGE_MULTIPLIER))
        return bite_damage, dot_damage, claw_damage

    async def _check_for_levelup(self, username: str, user_data: dict) -> bool:
        """Check and process level-ups. Returns True if leveled up."""
        class_name = user_data.get("class_name", "Derp Clone")
        
        # Only Tier 1 classes level up (not Monk or Derp Clone)
        if class_name == "Monk" or class_name == "Derp Clone" or class_name is None:
            return False
        
        total_xp = int(user_data.get("xp", 0))
        old_level = self._get_level_from_xp(total_xp - 1, user_data) if total_xp > 0 else 1  # What level they were at before this XP gain
        new_level = self._get_level_from_xp(total_xp, user_data)  # What level they are now
        
        if new_level > old_level:
            # Leveled up!
            user_data["player_level"] = new_level
            level_cap = self._get_level_cap(user_data)
            if new_level >= level_cap:
                # Ready to ascend
                await self._send_battle_message(f"@{username} reached level {level_cap}! Ready to ascend to Tier 2!")
                self._log_event(f"Level up: @{username} reached level {level_cap}. Ready for Tier 2 ascension.", battle=True)
            else:
                await self._send_battle_message(f"@{username} leveled up to {new_level}!")
                self._log_event(f"Level up: @{username} is now level {new_level}.", battle=True)
            return True
        return False

    def grant_salary(self, username: str, force: bool = False) -> tuple[bool, str]:
        state_obj = getattr(self, "_state_obj", None)
        if callable(state_obj):
            state_obj = state_obj()
        if state_obj is None:
            return False, "RPG state unavailable; try !reloadrpg."

        user = state_obj.get_user(username)
        current_stream_id = self._get_or_create_stream_id()
        claimed_stream_id = user.get("salary_claimed_stream_id")

        if claimed_stream_id is None and user.get("salary_claimed_this_stream"):
            claimed_stream_id = current_stream_id
            user["salary_claimed_stream_id"] = current_stream_id

        if str(claimed_stream_id) == str(current_stream_id) and not force:
            return False, "Salary already claimed this stream."
        gacha_tokens, entries = self._resolve_salary(user)
        raffle_cog = self._get_raffle_cog()
        if raffle_cog:
            raffle_cog.state.add_entries(username, entries)
        # Grant gacha tokens to user
        user["class_change_tokens"] = int(user.get("class_change_tokens", 0)) + gacha_tokens
        if not force:
            user["salary_claimed_this_stream"] = True
            user["salary_claimed_stream_id"] = current_stream_id
        state_obj.save_state()
        self._log_event(f"Salary: @{username} +{gacha_tokens} gacha tokens, +{entries} entries.")
        self._broadcast_state()
        return True, f"Salary granted: +{gacha_tokens} gacha tokens, +{entries} entries."

    def _grant_salary_diff(self, username: str, previous_tier: int) -> tuple[int, int]:
        user = self.state.get_user(username)
        if user.get("is_revenant"):
            return (0, 0)
        new_tier = int(user.get("class_tier", 0))
        prev_salary = CLASS_TIER_SALARIES.get(previous_tier, (0, 0))
        next_salary = CLASS_TIER_SALARIES.get(new_tier, (0, 0))
        diff_gacha_tokens = max(0, next_salary[0] - prev_salary[0])
        diff_entries = max(0, next_salary[1] - prev_salary[1])
        if diff_gacha_tokens == 0 and diff_entries == 0:
            return (0, 0)
        raffle_cog = self._get_raffle_cog()
        if raffle_cog:
            raffle_cog.state.add_entries(username, diff_entries)
        # Grant gacha tokens to user
        user["class_change_tokens"] = int(user.get("class_change_tokens", 0)) + diff_gacha_tokens
        self._log_event(
            f"Salary diff: @{username} +{diff_gacha_tokens} gacha tokens, +{diff_entries} entries."
        )
        return (diff_gacha_tokens, diff_entries)

    def _reset_stream_state(self):
        session = self.state.session()
        self._start_new_stream_session()
        self._clear_alchemist_brew_bonuses()
        session["battle_active"] = False
        session["battle_id"] = None
        session["monsters"] = []
        session["turn_number"] = 0
        session["phase"] = "idle"
        session["action_window_end"] = None
        session["join_window_end"] = None
        session["participants"] = []
        session["action_queue"] = []
        session["totems"] = []
        session["imps"] = []
        session["dragons"] = []
        session["green_arrows"] = []
        session["undead_pets"] = []
        session["streamer_pets"] = []
        session["buff_pets"] = []
        session["spirit_wells"] = []
        session["deputy_donut_rounds_remaining"] = 0
        session["barbarian_shout_rounds_remaining"] = 0
        session["battle_stat_baseline"] = {}
        session["slow_actions"] = False
        users = self.state.state.get("users", {})
        for username, user in users.items():
            user["active_player"] = False
            user["salary_claimed_this_stream"] = False
            user["salary_claimed_stream_id"] = None
            user["revenant_doom_cooldown"] = 0
            user["barbarian_whirlwind_cooldown"] = 0
            user["stream_usage"] = {}
            user["guard_active"] = False
            user["summoner_dot_damage"] = 0
            user["summoner_dot_rounds_remaining"] = 0
            user["buff_takeoff_used"] = False
            user["buff_kid_intercept_triggered"] = False
            user["buff_franklin_crit_triggered"] = False
            user["buff_franklin_jdam_buff_triggered"] = False
            user["buff_jdam_crit_triggered"] = False
            user["buff_jdam_forced_crit_charges"] = 0
            if username == STREAMER_NAME.lower():
                user["active_player"] = True
        self._enforce_single_revenant()
        self.state.save_state()
        self._log_event("Stream reset: RPG state reset for new stream.")
        self._broadcast_state()

    def _rollover_stream_only(self):
        helper = getattr(self, "_state_obj", None)
        state_obj = helper() if callable(helper) else None
        if state_obj is None and isinstance(self, RpgState):
            state_obj = self
        if state_obj is None:
            self.logger.warning("[RPG] _rollover_stream_only: state unavailable")
            return

        self._start_new_stream_session()
        self._clear_alchemist_brew_bonuses()
        users = state_obj.state.get("users", {})
        for username, user in users.items():
            user["active_player"] = False
            user["salary_claimed_this_stream"] = False
            user["salary_claimed_stream_id"] = None
            user["revenant_doom_cooldown"] = 0
            user["daily_embark_ts"] = None
            user["stream_usage"] = {}
            user["guard_active"] = False
            user["summoner_dot_damage"] = 0
            user["summoner_dot_rounds_remaining"] = 0
            if username == STREAMER_NAME.lower():
                user["active_player"] = True

        if hasattr(state_obj, "save_state"):
            try:
                state_obj.save_state()
            except Exception:
                self.logger.warning("[RPG] newstream: failed to save state", exc_info=True)
        self._log_event("New stream started: salary and active flags reset.")
        self._broadcast_state()

    def _expire_revenant(self, user: dict, award_revenant_xp_bonus: bool = False) -> int:
        username = None
        for name, data in self.state.state.get("users", {}).items():
            if data is user:
                username = name
                break
        session = self.state.session()
        revenant_xp = max(
            int(session.get("revenant_class_xp", 0)),
            int(user.get("xp", 0)),
        )
        session["revenant_class_xp"] = revenant_xp
        personal_xp = int(user.get("xp_before_revenant", user.get("xp", 0)))
        revenant_xp_at_acquire = int(user.get("revenant_xp_at_acquire", revenant_xp))
        earned_delta = max(0, revenant_xp - revenant_xp_at_acquire)
        user["xp"] = personal_xp + earned_delta if award_revenant_xp_bonus else personal_xp
        previous_class = user.get("previous_class") or user.get("base_class", "Derp Clone")
        previous_tier = user.get("previous_tier")
        user["class_name"] = previous_class
        if previous_tier is not None:
            user["class_tier"] = previous_tier
        user["is_revenant"] = False
        user["revenant_remaining_uses"] = 0
        user["revenant_remaining_streams"] = 0
        user["revenant_bonus_uses_awarded"] = 0
        user["revenant_acquired_ts"] = None
        user["xp_before_revenant"] = None
        user["revenant_xp_at_acquire"] = None
        user["previous_class"] = None
        user["previous_tier"] = None
        session["revenant_class_xp"] = revenant_xp
        if username:
            if session.get("active_revenant") == username:
                session["active_revenant"] = None
        return earned_delta

    def _is_user_revenant(self, user: dict) -> bool:
        return bool(user.get("is_revenant") or user.get("class_name") == "Revenant")

    def _normalize_revenant_user(self, username: str, user: dict):
        current_xp = int(user.get("xp", 0))
        session = self.session()
        revenant_class_xp = int(session.get("revenant_class_xp", 0))
        if revenant_class_xp <= 0:
            revenant_class_xp = current_xp
            session["revenant_class_xp"] = revenant_class_xp
        if user.get("class_name") != "Revenant":
            user["class_name"] = "Revenant"
        user["is_revenant"] = True
        user["xp"] = revenant_class_xp
        if user.get("previous_class") in (None, "Revenant"):
            user["previous_class"] = user.get("base_class", "Derp Clone")
        if user.get("previous_tier") is None:
            user["previous_tier"] = user.get("class_tier")
        if user.get("xp_before_revenant") is None:
            user["xp_before_revenant"] = current_xp
        if user.get("revenant_xp_at_acquire") is None:
            user["revenant_xp_at_acquire"] = revenant_class_xp
        if user.get("revenant_acquired_ts") is None:
            user["revenant_acquired_ts"] = _now_ts()
        session["active_revenant"] = username

    def _is_revenant_pass_due(self, user: dict, now_ts: int | None = None) -> bool:
        if not self._is_user_revenant(user):
            return False
        acquired_ts = user.get("revenant_acquired_ts")
        if acquired_ts is None:
            return False
        if now_ts is None:
            now_ts = _now_ts()
        return int(now_ts) >= int(acquired_ts) + REVENANT_DURATION_SECONDS

    def _transfer_revenant(self, from_username: str, to_username: str) -> tuple[bool, str]:
        from_username = from_username.lower()
        to_username = to_username.lower()
        users = self.state.state.setdefault("users", {})
        if from_username == to_username:
            return False, "You must pass Revenant to someone else."
        if from_username not in users:
            return False, "Current revenant holder not found."
        from_user = users[from_username]
        if not self._is_user_revenant(from_user):
            return False, "Only the active Revenant can pass the class."

        target_user = self.state.get_user(to_username)
        if self._is_user_revenant(target_user):
            return False, f"@{to_username} is already Revenant."
        if int(target_user.get("class_tier", 0)) < 1:
            return False, f"@{to_username} must be an ascended class to receive Revenant."

        self._enforce_single_revenant()
        if self._get_active_revenant_username() != from_username:
            return False, "Only the active Revenant holder can pass the class right now."

        gained_on_revenant = self._expire_revenant(from_user, award_revenant_xp_bonus=True)

        session = self.state.session()
        revenant_xp = max(
            int(session.get("revenant_class_xp", 0)),
            int(from_user.get("xp", 0)),
        )
        session["revenant_class_xp"] = revenant_xp
        history = session.setdefault("revenant_history", [])
        history.append(to_username)
        session["revenant_history"] = history[-3:]
        session["active_revenant"] = to_username

        target_user["xp_before_revenant"] = int(target_user.get("xp", 0))
        target_user["previous_class"] = target_user.get("class_name")
        target_user["previous_tier"] = target_user.get("class_tier")
        target_user["class_name"] = "Revenant"
        target_user["is_revenant"] = True
        target_user["revenant_remaining_uses"] = 15
        target_user["revenant_remaining_streams"] = REVENANT_STREAMS_DURATION
        target_user["revenant_bonus_uses_awarded"] = 0
        target_user["revenant_acquired_ts"] = _now_ts()
        target_user["revenant_xp_at_acquire"] = revenant_xp
        target_user["xp"] = revenant_xp

        self.state.save_state()
        self._log_event(
            f"Revenant passed: @{from_username} passed Revenant to @{to_username}. Revenant XP retained at {revenant_xp}."
        )
        self._broadcast_state()
        return True, f"@{from_username} passed Revenant to @{to_username}. @{from_username} gained +{gained_on_revenant} XP on their original class."

    def _get_active_revenant_username(self) -> str | None:
        users = self.state.state.get("users", {})
        active = [name for name, data in users.items() if self._is_user_revenant(data)]
        if not active:
            return None
        session_active = self.state.session().get("active_revenant")
        if session_active in active:
            return session_active
        history = self.state.session().get("revenant_history", [])
        if history:
            last = history[-1].lower()
            if last in active:
                return last
        return active[0]

    def _enforce_single_revenant(self):
        users = self.state.state.get("users", {})
        active = [name for name, data in users.items() if self._is_user_revenant(data)]
        if len(active) <= 1:
            if active:
                self._normalize_revenant_user(active[0], users[active[0]])
            else:
                self.state.session()["active_revenant"] = None
            return
        keep = self._get_active_revenant_username()
        for name in active:
            if name != keep:
                self._expire_revenant(users[name])
        if keep and keep in users:
            self._normalize_revenant_user(keep, users[keep])
        else:
            self.state.session()["active_revenant"] = None

    def _eligible_for_revenant(self, username: str, user: dict) -> bool:
        if not REVENANT_NEW_GRANTS_ENABLED:
            return False
        if self._is_user_revenant(user):
            return False
        if not user.get("active_player"):
            return False
        if self._get_active_revenant_username():
            return False
        if int(user.get("class_tier", 0)) < 1:
            return False
        history = self.state.session().get("revenant_history", [])[-3:]
        return username not in history

    async def _grant_revenant(self, username: str, user: dict):
        self._enforce_single_revenant()
        active = self._get_active_revenant_username()
        if active and active != username:
            return False
        session = self.state.session()
        current_xp = int(user.get("xp", 0))
        revenant_class_xp = max(int(session.get("revenant_class_xp", 0)), current_xp)
        session["revenant_class_xp"] = revenant_class_xp
        history = session.setdefault("revenant_history", [])
        history.append(username)
        session["revenant_history"] = history[-3:]
        session["active_revenant"] = username
        previous_class = user.get("class_name")
        if previous_class == "Revenant":
            previous_class = user.get("base_class", "Derp Clone")
        user["previous_class"] = previous_class
        user["previous_tier"] = user.get("class_tier")
        user["xp_before_revenant"] = current_xp
        user["class_name"] = "Revenant"
        user["is_revenant"] = True
        user["xp"] = revenant_class_xp
        user["revenant_xp_at_acquire"] = revenant_class_xp
        user["revenant_remaining_uses"] = 15
        user["revenant_remaining_streams"] = REVENANT_STREAMS_DURATION
        user["revenant_bonus_uses_awarded"] = 0
        user["revenant_acquired_ts"] = _now_ts()
        gacha_tokens, entries = MYTHIC_SALARY
        raffle_cog = self._get_raffle_cog()
        if raffle_cog:
            raffle_cog.state.add_entries(username, entries)
        user["class_change_tokens"] = int(user.get("class_change_tokens", 0)) + gacha_tokens
        self.state.save_state()
        self._log_event(
            f"Mythic: @{username} has awakened. +{gacha_tokens} gacha tokens, +{entries} entries."
        )
        await self._send_battle_message(
            f"@{username} has awakened as a Revenant! +{gacha_tokens} gacha tokens, +{entries} entries."
        )
        self._broadcast_state()
        return True

    # TODO: Remove unused helper (commented out): _queue_action
    # def _queue_action(self, username: str, action: str, damage: int):
    #     session = self.state.session()
    #     session.setdefault("action_queue", []).append({
    #         "user": username,
    #         "action": action,
    #         "damage": damage,
    #         "ts": _now_ts(),
    #     })
    #     self.state.save_state()

    def _get_active_monster(self, session: dict):
        alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
        if not alive_monsters:
            return None
        # Return the lowest-HP monster (focus fire strategy)
        return min(alive_monsters, key=lambda m: int(m.get("hp", 0)))

    def _get_monster_by_index(self, session: dict, index: int):
        for monster in session.get("monsters", []):
            if int(monster.get("index", 0)) == int(index) and monster.get("alive"):
                return monster
        return None

    def _monster_has_revenant_doom_status(self, monster: dict) -> bool:
        return any([
            int(monster.get("corruption_rounds_remaining", 0)) > 0,
            int(monster.get("ghoul_poison_rounds_remaining", 0)) > 0,
            int(monster.get("gross_out_rounds_remaining", 0)) > 0,
            int(monster.get("bleed_rounds_remaining", 0)) > 0,
            int(monster.get("bleed_stacks", 0)) > 0,
            int(monster.get("stun_turns_remaining", 0)) > 0,
            int(monster.get("berzerk_turns_remaining", 0)) > 0,
        ])

    def _build_monster_entry(self, name: str, level: int, index: int) -> dict:
        skeleton_pets = {SKELEMAGE_NAME, SKELEROG_NAME, SKELEPRIEST_NAME, SKELETANK_NAME}
        skill_power = 3 + max(0, level - 1)
        if name == SQUIRREL_NAME:
            level = SQUIRREL_LEVEL
            max_hp = SQUIRREL_HP
        elif name == SUMMONER_NAME:
            max_hp = MONSTER_BASE_HP + 10 + (level - 1) * (MONSTER_HP_PER_LEVEL + 1)
        elif name == SKELEMAGE_NAME:
            max_hp = 10 + (level - 1) * 2
        elif name == SKELEROG_NAME:
            max_hp = 9 + (level - 1) * 2
        elif name == SKELEPRIEST_NAME:
            max_hp = 11 + (level - 1) * 2
        elif name == SKELETANK_NAME:
            max_hp = 18 + (level - 1) * 3
        else:
            max_hp = MONSTER_BASE_HP + (level - 1) * MONSTER_HP_PER_LEVEL
        entry = {
            "id": f"{name}_{_now_ts()}_{index}",
            "index": index,
            "name": name,
            "level": level,
            "hp": max_hp,
            "max_hp": max_hp,
            "alive": True,
            "bleed_stacks": 0,
            "bleed_rounds_remaining": 0,
            "stun_turns_remaining": 0,
            "corruption_damage": 0,
            "corruption_rounds_remaining": 0,
            "dragon_dot_damage": 0,
            "dragon_dot_rounds_remaining": 0,
            "gross_out_damage": 0,
            "gross_out_rounds_remaining": 0,
            "ghoul_poison_damage": 0,
            "ghoul_poison_rounds_remaining": 0,
            "berzerk_turns_remaining": 0,
            "drunk_turns_remaining": 0,
            "hungover_active": False,
            "is_loot_goblin": False,
        }
        if name in skeleton_pets:
            if name == SKELEMAGE_NAME:
                entry["custom_damage"] = max(1, skill_power - 1)
            elif name == SKELEROG_NAME:
                entry["custom_damage"] = skill_power
            elif name == SKELEPRIEST_NAME:
                entry["custom_damage"] = max(1, skill_power - 2)
            elif name == SKELETANK_NAME:
                entry["custom_damage"] = max(1, skill_power - 2)
            entry["is_summoner_pet"] = True
        elif name == SUMMONER_NAME:
            entry["custom_damage"] = max(1, skill_power - 1)
        return entry

    def _build_loot_goblin_entry(self, index: int, level: int = 1) -> dict:
        goblin_level = max(1, int(level or 1))
        goblin_max_hp = LOOT_GOBLIN_HP + ((goblin_level - 1) * MONSTER_HP_PER_LEVEL)
        return {
            "id": f"LootGoblin_{_now_ts()}_{index}",
            "index": index,
            "name": "Loot Goblin",
            "level": goblin_level,
            "hp": goblin_max_hp,
            "max_hp": goblin_max_hp,
            "alive": True,
            "bleed_stacks": 0,
            "bleed_rounds_remaining": 0,
            "stun_turns_remaining": 0,
            "corruption_damage": 0,
            "corruption_rounds_remaining": 0,
            "dragon_dot_damage": 0,
            "dragon_dot_rounds_remaining": 0,
            "ghoul_poison_damage": 0,
            "ghoul_poison_rounds_remaining": 0,
            "berzerk_turns_remaining": 0,
            "drunk_turns_remaining": 0,
            "hungover_active": False,
            "is_loot_goblin": True,
        }

    def _get_loot_goblin_rewards(self, monster_level: int) -> tuple[int, int, int]:
        level = max(1, int(monster_level or 1))
        team_bonus = min(LOOT_GOBLIN_REWARD_SCALE_BONUS_CAP, (level - 1) // LOOT_GOBLIN_REWARD_SCALE_TEAM_EVERY)
        killer_bonus = min(LOOT_GOBLIN_REWARD_SCALE_BONUS_CAP, (level - 1) // LOOT_GOBLIN_REWARD_SCALE_KILLER_EVERY)
        entries_bonus = min(LOOT_GOBLIN_REWARD_SCALE_BONUS_CAP, (level - 1) // LOOT_GOBLIN_REWARD_SCALE_ENTRIES_EVERY)
        team_gacha = LOOT_GOBLIN_GACHA_REWARD + team_bonus
        killer_gacha = LOOT_GOBLIN_KILLER_GACHA + killer_bonus
        entries_min = LOOT_GOBLIN_KILLER_ENTRIES_MIN + entries_bonus
        entries_max = LOOT_GOBLIN_KILLER_ENTRIES_MAX + entries_bonus
        killer_entries = random.randint(entries_min, entries_max)
        return team_gacha, killer_gacha, killer_entries

    async def _award_loot_goblin_rewards(self, session: dict, killer_username: str, monster_level: int, by_imp: bool = False):
        participants = session.get("participants", [])
        team_gacha, killer_gacha, killer_entries = self._get_loot_goblin_rewards(monster_level)

        for participant in participants:
            p_user = self.state.get_user(participant)
            p_user["class_change_tokens"] = int(p_user.get("class_change_tokens", 0)) + team_gacha

        killer_user = self.state.get_user(killer_username)
        killer_user["class_change_tokens"] = int(killer_user.get("class_change_tokens", 0)) + killer_gacha

        raffle_cog = self._get_raffle_cog()
        if raffle_cog:
            raffle_cog.state.add_entries(killer_username, killer_entries)

        if by_imp:
            self._log_event(
                f"Loot Goblin slain by imp! Everyone gets {team_gacha} gacha tokens. @{killer_username} gets +{killer_gacha} gacha tokens and {killer_entries} raffle entries!",
                battle=True,
            )
            await self._send_battle_message(
                f"ðŸŽ‰ Loot Goblin defeated by @{killer_username}'s imp! Everyone gets {team_gacha} gacha tokens! @{killer_username} gets +{killer_gacha} gacha and {killer_entries} entries! ðŸŽ‰"
            )
        else:
            self._log_event(
                f"Loot Goblin slain! Everyone gets {team_gacha} gacha tokens. @{killer_username} gets +{killer_gacha} gacha tokens and {killer_entries} raffle entries!",
                battle=True,
            )
            await self._send_battle_message(
                f"ðŸŽ‰ Loot Goblin defeated! Everyone gets {team_gacha} gacha tokens! @{killer_username} gets +{killer_gacha} gacha and {killer_entries} entries! ðŸŽ‰"
            )

    def _cleanup_dead_summoner_pets(self, session: dict) -> int:
        monsters = session.get("monsters", [])
        alive_by_id = {
            str(m.get("id")): bool(m.get("alive"))
            for m in monsters
            if m.get("id")
        }
        removed = 0
        for pet in monsters:
            if not pet.get("alive") or not pet.get("is_summoner_pet"):
                continue
            owner_id = str(pet.get("summoned_by") or "")
            if owner_id and not alive_by_id.get(owner_id, False):
                pet["alive"] = False
                removed += 1
        if removed > 0:
            self._log_event(
                f"Summoner collapse: {removed} summoned skeleton(s) crumbled with their master.",
                battle=True,
            )
        return removed

    def _choose_summoner_pet_type(self, session: dict, active_pets: list[dict]) -> str:
        alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
        alive_players = [
            name for name in session.get("participants", [])
            if int(self.state.get_user(name).get("hp_current", 0)) > 0
        ]

        active_types = {str(p.get("name", "")).lower() for p in active_pets}

        if SKELETANK_NAME not in active_types and len(alive_players) >= 2:
            return SKELETANK_NAME

        wounded_allies = [
            m for m in alive_monsters
            if int(m.get("hp", 0)) < int(m.get("max_hp", 0))
        ]
        if wounded_allies and SKELEPRIEST_NAME not in active_types:
            return SKELEPRIEST_NAME

        uncorrupted_players = [
            name for name in alive_players
            if int(self.state.get_user(name).get("summoner_dot_rounds_remaining", 0)) <= 0
        ]
        if uncorrupted_players:
            return SKELEMAGE_NAME

        return random.choice([SKELEMAGE_NAME, SKELEROG_NAME, SKELEPRIEST_NAME, SKELETANK_NAME])

    def _get_alive_participants(self, session: dict):
        """Get list of participants who are still alive (hp_current > 0)"""
        participants = session.get("participants", [])
        alive = []
        for user in participants:
            user_data = self.state.get_user(user)
            current_hp = int(user_data.get("hp_current", DEFAULT_PLAYER_HP))
            if current_hp > 0:
                alive.append(user)
        return alive

    def _get_totem_buff(self, session: dict) -> dict:
        """Get the buff from active totems. Returns dict with buff_type and values."""
        totems = [t for t in session.get("totems", []) if t.get("alive")]
        if not totems:
            return {
                "buff_type": None,
                "is_killshot": False,
                "is_autocrit": False,
                "has_shield": False,
                "has_healing": False,
                "damage_bonus": 0,
            }

        active_types = {
            str(t.get("buff_type", "")).strip().lower()
            for t in totems
        }
        damage_totems = [
            t for t in totems
            if str(t.get("buff_type", "")).strip().lower() in {"damage_1", "damage_5"}
        ]
        damage_bonus = 0
        if damage_totems:
            damage_bonus = max(self._get_totem_damage_bonus(t) for t in damage_totems)

        return {
            "buff_type": "/".join(sorted(active_types)) if active_types else None,
            "is_killshot": "killshot" in active_types,
            "is_autocrit": "autocrit" in active_types,
            "has_shield": "shield" in active_types,
            "has_healing": "healing" in active_types,
            "damage_bonus": damage_bonus,
        }

    def _get_totem_damage_bonus(self, totem: dict) -> int:
        buff_type = str(totem.get("buff_type", "")).strip().lower()
        if buff_type not in {"damage_1", "damage_5"}:
            return 0
        owner = str(totem.get("owner", "")).strip().lower()
        owner_data = self.state.get_user(owner) if owner else {}
        owner_level = self._get_level_from_xp(int(owner_data.get("xp", 0)), owner_data)
        if buff_type == "damage_1":
            return 1 + max(0, owner_level - 1)
        return 5 + (2 * max(0, owner_level - 1))

    def _get_totem_label(self, totem: dict) -> str:
        buff_type = str(totem.get("buff_type", "")).strip().lower()
        if buff_type in {"damage_1", "damage_5"}:
            return f"+{self._get_totem_damage_bonus(totem)} damage"
        return TOTEM_LABELS.get(buff_type, "Totem")

    def _refresh_party_shields_from_totem(self, session: dict):
        totem_buff = self._get_totem_buff(session)
        shield_active = bool(totem_buff.get("has_shield"))

        for username in session.get("participants", []):
            user_data = self.state.get_user(username)
            user_data["totem_shield_available"] = shield_active and int(user_data.get("hp_current", 0)) > 0

        for group_name in ["totems", "imps", "green_arrows", "dragons", "undead_pets", "streamer_pets", "spirit_wells"]:
            for entity in session.get(group_name, []):
                entity["totem_shield_available"] = shield_active and bool(entity.get("alive"))

        for entity in session.get("buff_pets", []):
            entity["totem_shield_available"] = shield_active and bool(entity.get("alive"))

    async def _apply_healing_totem_pulse(self, session: dict):
        """Apply a small heal to all alive participants when a healing totem is active."""
        totem_buff = self._get_totem_buff(session)
        if not totem_buff.get("has_healing"):
            return
        participants = session.get("participants", [])
        for username in participants:
            user_data = self.state.get_user(username)
            if int(user_data.get("hp_current", 0)) <= 0:
                continue
            max_hp = int(user_data.get("hp_max", DEFAULT_PLAYER_HP))
            heal_amount = max(1, int(max_hp * 0.02))  # 2% max HP minimum 1
            user_data["hp_current"] = min(max_hp, int(user_data.get("hp_current", 0)) + heal_amount)
        try:
            self.state.save_state()
        except Exception:
            self.logger.warning("[RPG] Failed to save state during healing totem pulse", exc_info=True)

    async def _apply_meatwad_passive_effects(self, session: dict):
        """Apply passive effects from Meatwad transformations at start of turn."""
        participants = session.get("participants", [])

        for username in participants:
            user_data = self.state.get_user(username)

        # Only process if user has a transformation active
            form_data = user_data.get("meatwad_form")
            if not form_data:
                continue

            current_hp = int(user_data.get("hp_current", DEFAULT_PLAYER_HP))
            if current_hp <= 0:
                continue  # Dead players don't get passive effects

            form_name = form_data.get("name", "Unknown")
            effect_type = form_data.get("effect_type", "")
            effect_value = form_data.get("effect_value", 0)

        # Apply effect based on type
            if effect_type == "heal_self" or effect_type == "regen":
                max_hp = int(user_data.get("hp_max", DEFAULT_PLAYER_HP))
                new_hp = min(max_hp, current_hp + int(effect_value))
                healed = new_hp - current_hp
                if healed > 0:
                    user_data["hp_current"] = new_hp
                    user_data["healing_done"] = int(user_data.get("healing_done", 0)) + healed
                    await self._send_battle_message(f"{form_name}: @{username} regenerates {healed} HP")
                    self._log_event(f"Meatwad passive: @{username} as {form_name} healed {healed} HP.", battle=True)

            elif effect_type == "heal_party":
                heal_amount = int(effect_value)
                total_healed = 0
                for participant in participants:
                    participant_data = self.state.get_user(participant)
                    p_current_hp = int(participant_data.get("hp_current", DEFAULT_PLAYER_HP))
                    if p_current_hp > 0:
                        p_max_hp = int(participant_data.get("hp_max", DEFAULT_PLAYER_HP))
                        p_new_hp = min(p_max_hp, p_current_hp + heal_amount)
                        healed = p_new_hp - p_current_hp
                        if healed > 0:
                            participant_data["hp_current"] = p_new_hp
                            total_healed += healed
                if total_healed > 0:
                    await self._send_battle_message(f"{form_name}: @{username}'s aura heals party for {total_healed} total HP")
                    self._log_event(f"Meatwad passive: @{username} as {form_name} healed party for {total_healed} HP.", battle=True)

            elif effect_type == "hp_boost":
                boost_value = int(effect_value)
                if not form_data.get("boost_applied"):
                    user_data["hp_max"] = int(user_data.get("hp_max", DEFAULT_PLAYER_HP)) + boost_value
                    user_data["hp_current"] = int(user_data.get("hp_current", DEFAULT_PLAYER_HP)) + boost_value
                    form_data["boost_applied"] = True
                    user_data["meatwad_form"] = form_data
                    await self._send_battle_message(f"{form_name}: @{username} grows massive! +{boost_value} max HP")
                    self._log_event(f"Meatwad passive: @{username} as {form_name} gained {boost_value} max HP.", battle=True)

            elif effect_type == "dot":
                dot_damage = int(effect_value)
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                for monster in alive_monsters:
                    hp_before = int(monster.get("hp", 0))
                    dealt = min(dot_damage, hp_before)
                    monster["hp"] = max(0, hp_before - dot_damage)
                    if dealt > 0:
                        user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + dealt
                        user_data["damage_done"] = int(user_data.get("damage_done", 0)) + dealt
                    if monster.get("hp", 0) <= 0 and monster.get("alive"):
                        monster["alive"] = False
                        monster["killed_by"] = username
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                if alive_monsters:
                    await self._send_battle_message(f"{form_name}: @{username} poisons all enemies for {dot_damage} damage")
                    self._log_event(f"Meatwad passive: @{username} as {form_name} poisoned enemies.", battle=True)

            elif effect_type == "aoe":
                aoe_damage = int(effect_value)
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                total_dealt = 0
                for monster in alive_monsters:
                    hp_before = int(monster.get("hp", 0))
                    dealt = min(aoe_damage, hp_before)
                    monster["hp"] = max(0, hp_before - aoe_damage)
                    total_dealt += dealt
                    if monster.get("hp", 0) <= 0 and monster.get("alive"):
                        monster["alive"] = False
                        monster["killed_by"] = username
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                if total_dealt > 0:
                    user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_dealt
                    user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_dealt
                    await self._send_battle_message(f"{form_name}: @{username} whirls for {aoe_damage} damage to all enemies!")
                    self._log_event(f"Meatwad passive: @{username} as {form_name} dealt {total_dealt} AoE damage.", battle=True)

    # Note: reflect, defense, damage, party_damage, party_defense, evasion, crit_chance, counter, balanced, five_boost, chaos
    # are handled during damage calculation/monster attacks, not here

    async def _battle_loop_impl(self):
        await self.bot.wait_for_ready()
        while True:
            await asyncio.sleep(1)
            session = self.state.session()
            if not session.get("battle_active"):
                continue
            now_ts = _now_ts()
            if session.get("phase") == "join":
                join_end = session.get("join_window_end")
                if join_end and now_ts >= int(join_end):
                    session["phase"] = "action"
                    session["action_window_end"] = _now_ts() + ACTION_WINDOW_SECONDS
                    self.state.save_state()
                    self._log_event("Action window opened.", battle=True)
                    self._broadcast_state()
                    await self._send_battle_message("Action window open. Submit your battle command now!")
                continue
            action_end = session.get("action_window_end")
            if session.get("phase") == "action" and action_end:
                turn_number = int(session.get("turn_number", 0))
                auto_dispatch_turn = int(session.get("auto_join_dispatch_turn", -1))
                early_dispatch_at = int(action_end) - max(0, int(ACTION_WINDOW_SECONDS) - 30)
                if auto_dispatch_turn != turn_number and now_ts >= early_dispatch_at:
                    queued_early = await self._queue_join_auto_actions(announce_reason="join auto timer")
                    session["auto_join_dispatch_turn"] = turn_number
                    if queued_early > 0:
                        self.state.save_state()
                        self._broadcast_state()
                        participants = session.get("participants", [])
                        queued_users = {entry.get("user") for entry in session.get("action_queue", [])}
                        alive_participants = [
                            name for name in participants
                            if int(self.state.get_user(name).get("hp_current", 0)) > 0
                        ]
                        if alive_participants and all(user in queued_users for user in alive_participants):
                            try:
                                await self._resolve_turn()
                            except Exception:
                                logging.error("Resolve turn failed.", exc_info=True)
                            continue
                    self.state.save_state()

            if action_end and now_ts >= int(action_end):
                try:
                    await self._resolve_turn()
                except Exception:
                    logging.error("Resolve turn failed.", exc_info=True)

    def _build_auto_action(self, username: str, user_data: dict):
        class_name = str(user_data.get("class_name", "Derp Clone")).strip()
        if self._is_user_revenant(user_data):
            class_name = "Revenant"

        options = AUTO_CLASS_ACTIONS.get(class_name)
        if not options:
            return (None, "none")
        action_name, base_damage = random.choice(options)
        if not action_name or action_name == "none" or action_name == "transform":
            return (None, "none")

        half_damage = int(base_damage) // 2 if int(base_damage) > 0 else 0
        if int(base_damage) > 0:
            half_damage = max(1, half_damage)

        return ({
            "user": username,
            "action": action_name,
            "damage": half_damage,
            "target_index": None,
            "ts": _now_ts(),
        }, action_name)

    async def _queue_join_auto_actions(self, state_obj=None, announce_reason: str = "join auto") -> int:
        state_obj = state_obj or self._state_obj()
        if state_obj is None:
            self.logger.warning("[RPG] auto-actions skipped: state unavailable")
            return 0
        session = state_obj.session()
        action_queue = session.get("action_queue", [])
        queued_users = {entry.get("user") for entry in action_queue}
        participants = session.get("participants", [])
        auto_join_modes = session.get("auto_join_modes", {})
        queued_count = 0

        for username in participants:
            if username in queued_users:
                continue

            auto_mode = str(auto_join_modes.get(username, "")).strip().lower()
            if auto_mode != "primary_half":
                continue

            user_data = state_obj.get_user(username)
            auto_action, auto_name = self._build_auto_action(username, user_data)
            if not auto_action:
                continue

            action_queue.append(auto_action)
            queued_users.add(username)
            queued_count += 1
            self._log_event(
                f"Default action: @{username} auto-used {auto_name} ({announce_reason}).",
                battle=True,
            )
            await self._send_battle_message(
                f"@{username} auto-used {auto_name} at half strength."
            )

        return queued_count

    def _action_delay_seconds(self, session: dict) -> float:
        return 1.0 if session.get("slow_actions") else 0.0

    async def _ensure_action_window_open(self, battle_id: str, join_end_ts: int):
        """Fallback timer: flip join->action if the main battle loop misses the boundary."""
        try:
            sleep_for = max(0, int(join_end_ts) - _now_ts())
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            session = self.state.session()
            if not session.get("battle_active"):
                return
            if session.get("battle_id") != battle_id:
                return
            if session.get("phase") != "join":
                return
            session["phase"] = "action"
            session["action_window_end"] = _now_ts() + ACTION_WINDOW_SECONDS
            self.state.save_state()
            self._log_event("Action window opened (fallback timer).", battle=True)
            self._broadcast_state()
            await self._send_battle_message("Action window open. Submit your battle command now!")
        except Exception:
            self.logger.warning("[RPG] _ensure_action_window_open failed", exc_info=True)

    async def _maybe_action_delay(self, session: dict):
        delay_seconds = self._action_delay_seconds(session)
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    def _log_event(self, text: str, *, battle: bool = False):
        state_obj = getattr(self, "state", None)
        log_store = None
        if hasattr(state_obj, "log"):
            log_store = state_obj.log
        elif isinstance(state_obj, dict):
            log_store = state_obj.setdefault("log", {"daily_log": [], "battle_log": []})
        if log_store is None:
            return

        entry = {"ts": _utc_iso(), "text": text}
        daily_log = log_store.setdefault("daily_log", [])
        daily_log.append(entry)
        if len(daily_log) > LOG_LIMIT:
            del daily_log[: len(daily_log) - LOG_LIMIT]
        if battle:
            battle_entry = {"ts": entry["ts"], "text": text}
            battle_log = log_store.setdefault("battle_log", [])
            battle_log.append(battle_entry)
            if len(battle_log) > BATTLE_LOG_LIMIT:
                del battle_log[: len(battle_log) - BATTLE_LOG_LIMIT]
        if hasattr(state_obj, "save_log"):
            try:
                state_obj.save_log()
            except Exception:
                self.logger.warning("Failed to persist RPG log", exc_info=True)

    def _broadcast_state(self):
        try:
            payload = self._build_overlay_payload()
        except AttributeError:
            self.logger.warning("RPG overlay payload builder failed (AttributeError); skipping broadcast.", exc_info=True)
            return
        except Exception:
            self.logger.warning("Failed to build RPG overlay payload", exc_info=True)
            return
        if not payload:
            return
        try:
            asyncio.create_task(broadcast_overlay_message(payload))
        except RuntimeError:
            pass
        except Exception:
            self.logger.warning("Failed to broadcast RPG state", exc_info=True)
        # Also refresh the cached latest state on the overlay server so pull clients stay in sync
        try:
            asyncio.create_task(broadcast_overlay_message(payload))
        except Exception:
            pass

    async def _send_battle_message(self, text: str):
        payload = {"type": "ticker", "text": text}
        try:
            await broadcast_overlay_message(payload)
        except Exception:
            self.logger.warning("Failed to broadcast RPG battle message", exc_info=True)

    def _get_donut_effectiveness_multiplier(self, session: dict = None) -> float:
        if not session:
            return 1.0
        multiplier = 1.0
        donut_rounds = int(session.get("deputy_donut_rounds_remaining", 0))
        if donut_rounds > 0:
            multiplier *= DEPUTY_DONUT_EFFECTIVENESS_MULTIPLIER
        barbarian_shout_rounds = int(session.get("barbarian_shout_rounds_remaining", 0))
        if barbarian_shout_rounds > 0:
            multiplier *= BARBARIAN_SHOUT_DAMAGE_MULTIPLIER
        return multiplier

    def _tick_deputy_turn_state(self, state_obj, session: dict):
        participants = session.get("participants", [])
        for username in participants:
            user_data = state_obj.get_user(username)
            revenant_doom_cd = int(user_data.get("revenant_doom_cooldown", 0))
            if self._is_user_revenant(user_data) and revenant_doom_cd > 0:
                user_data["revenant_doom_cooldown"] = revenant_doom_cd - 1
            if str(user_data.get("class_name", "")).strip().lower() != "deputy":
                continue
            teargass_cd = int(user_data.get("deputy_teargass_cooldown", 0))
            donut_cd = int(user_data.get("deputy_donut_cooldown", 0))
            tommygun_cd = int(user_data.get("deputy_tommygun_cooldown", 0))
            whirlwind_cd = int(user_data.get("barbarian_whirlwind_cooldown", 0))
            if teargass_cd > 0:
                user_data["deputy_teargass_cooldown"] = teargass_cd - 1
            if donut_cd > 0:
                user_data["deputy_donut_cooldown"] = donut_cd - 1
            if tommygun_cd > 0:
                user_data["deputy_tommygun_cooldown"] = tommygun_cd - 1
            if whirlwind_cd > 0:
                user_data["barbarian_whirlwind_cooldown"] = whirlwind_cd - 1

        donut_rounds = int(session.get("deputy_donut_rounds_remaining", 0))
        if donut_rounds > 0:
            session["deputy_donut_rounds_remaining"] = donut_rounds - 1

        shout_rounds = int(session.get("barbarian_shout_rounds_remaining", 0))
        if shout_rounds > 0:
            session["barbarian_shout_rounds_remaining"] = shout_rounds - 1

    def _reset_deputy_battle_cooldowns(self, usernames: list[str]):
        for username in usernames:
            user_data = self.state.get_user(username)
            user_data["deputy_teargass_cooldown"] = 0
            user_data["deputy_donut_cooldown"] = 0
            user_data["deputy_tommygun_cooldown"] = 0
            user_data["barbarian_whirlwind_cooldown"] = 0
    
    async def _resolve_turn(self):
        state_obj = self._state_obj()
        if state_obj is None:
            self.logger.warning("[RPG] _resolve_turn skipped: state unavailable")
            return
        session = state_obj.session()
        if not session.get("battle_active"):
            return
        self._enforce_single_revenant()
        self._tick_deputy_turn_state(state_obj, session)
        
        # Give default actions to participants who didn't act
        action_queue = session.get("action_queue", [])
        queued_users = {entry.get("user") for entry in action_queue}
        participants = session.get("participants", [])
        await self._queue_join_auto_actions(state_obj, announce_reason="join auto")
        queued_users = {entry.get("user") for entry in action_queue}
        for username in participants:
            if username not in queued_users:
                user_data = state_obj.get_user(username)
                auto_mode = str(session.get("auto_join_modes", {}).get(username, "")).strip().lower()
    
                # Monks do not get a default action if they don't queue one
                if user_data.get("class_name") == "Monk":
                    continue
    
                if auto_mode == "primary_half":
                    auto_action, auto_name = self._build_auto_action(username, user_data)
                    if auto_action:
                        action_queue.append(auto_action)
                        self._log_event(
                            f"Default action: @{username} auto-used {auto_name} (join auto).",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"@{username} auto-used {auto_name} at half strength."
                        )
                    continue
                # Add a default bonk action for missing participants
                action_queue.append({
                    "user": username,
                    "action": "bonk",
                    "damage": 1,
                    "target_index": None,
                    "ts": _now_ts(),
                })
                self._log_event(f"Default action: @{username} bonked (no action submitted).", battle=True)
                await self._send_battle_message(f"@{username} took no action and bonked weakly.")
        
        # Track action count for each participant for XP rewards
        action_counts = {}
        for action in action_queue:
            user = action.get("user")
            action_counts[user] = action_counts.get(user, 0) + 1
        
        # Store action counts in session for later use in battle end
        session["turn_action_counts"] = action_counts
        
        action_queue = session.get("action_queue", [])
        if not action_queue:
            self._log_event("Turn resolved: no player actions.", battle=True)
        def action_order(entry: dict) -> int:
            user = entry.get("user")
            user_data = state_obj.get_user(user)
            class_name = user_data.get("class_name", "")
            action_name = entry.get("action")
            # Transform happens FIRST
            if action_name == "transform":
                return -1
            if action_name == "guard" or class_name == "Warrior":
                return 0
            if action_name == "restore" or class_name == "Healer":
                return 3
            return 1
    
        ordered_actions = sorted(action_queue, key=action_order)
        
        # Apply passive Meatwad transformation effects at start of turn
        await self._apply_meatwad_passive_effects(session)
        
        heal_actions = []  # Collect heal actions to process after monsters attack
        
        for action_index, action in enumerate(ordered_actions):
            if action_index > 0:
                await self._maybe_action_delay(session)
            user = action.get("user")
            damage = int(action.get("damage", 0))
            action_name = action.get("action")
            target_index = action.get("target_index")
            user_data = state_obj.get_user(user)
    
            hexed_turns = int(user_data.get("hexed_turns_remaining", 0))
            if hexed_turns > 0:
                user_data["hexed_turns_remaining"] = max(0, hexed_turns - 1)
                alive_allies = [
                    name for name in session.get("participants", [])
                    if name != user and int(state_obj.get_user(name).get("hp_current", 0)) > 0
                ]
                if alive_allies:
                    target_name = random.choice(alive_allies)
                    target_user = state_obj.get_user(target_name)
                    hp_before = int(target_user.get("hp_current", DEFAULT_PLAYER_HP))
                    target_user["hp_current"] = max(0, hp_before - HEX_FRIENDLY_DAMAGE)
                    self._log_event(
                        f"Hex: @{user} attacked @{target_name} for {HEX_FRIENDLY_DAMAGE} damage.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"@{user} is hexed and strikes @{target_name} for {HEX_FRIENDLY_DAMAGE}!"
                    )
                    if hp_before > 0 and target_user["hp_current"] == 0:
                        if not await self._trigger_archangel_death_passive(session, target_name):
                            target_user["times_knocked_out"] = int(target_user.get("times_knocked_out", 0)) + 1
                            despawned = self._despawn_buff_pets_for_owner(session, target_name)
                            if despawned:
                                await self._send_battle_message(
                                    f"ðŸ’¨ {', '.join(despawned)} vanish as @{target_name} is knocked out!"
                                )
                else:
                    self._log_event(f"Hex: @{user}'s hex fizzled (no allies to target).", battle=True)
                continue
            
            # Process taunt actions - mark warriors as taunting
            if action_name == "taunt":
                # Find the warrior and mark them for mandatory targeting
                session.setdefault("taunted_warriors", []).append(user)
                self._log_event(f"Action: @{user} taunted the enemies.", battle=True)
                await self._send_battle_message(f"@{user} taunted the enemies, forcing attacks on them!")
                continue
            
            # Process ohm actions - monk meditation that does nothing
            if action_name == "ohm":
                self._log_event(f"Action: @{user} meditated with ohm.", battle=True)
                await self._send_battle_message(f"@{user} glows with blessing energy, bolstering the party!")
                continue
            
            # Process transform actions - Meatwad transformation (form already saved)
            if action_name == "transform":
                form_data = action.get("form", {})
                form_name = form_data.get("name", "Unknown")
                self._log_event(f"Action: @{user} transformed into {form_name}.", battle=True)
                # Message already sent in command, just continue
                continue
            
            # Process streamer stream_heal - heals entire party
            if action_name == "stream_heal":
                participants = session.get("participants", [])
                user_data = self.state.get_user(user)
                streamer_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                heal_amount = STREAMER_HEAL_BASE + ((max(1, streamer_level) - 1) // STREAMER_HEAL_PER_LEVEL_STEP)
                heal_amount = max(1, int(heal_amount * self._get_donut_effectiveness_multiplier(session)))
                
                healed_count = 0
                total_healed = 0
                for participant in participants:
                    participant_data = self.state.get_user(participant)
                    current_hp = int(participant_data.get("hp_current", DEFAULT_PLAYER_HP))
                    max_hp = int(participant_data.get("hp_max", DEFAULT_PLAYER_HP))
                    
                    if current_hp > 0:  # Only heal alive party members
                        new_hp = min(max_hp, current_hp + heal_amount)
                        healed = new_hp - current_hp
                        participant_data["hp_current"] = new_hp
                        healed_count += 1
                        total_healed += healed
    
                    user_data["healing_done"] = int(user_data.get("healing_done", 0)) + total_healed
                
                self._log_event(f"Action: @{user} healed the party for {total_healed} total HP.", battle=True)
                await self._send_battle_message(f"@{user} healed the entire party for {total_healed} HP!")
                continue
            
            # Process streamer totem - already created in command, just log it
            if action_name == "totem":
                self._log_event(f"Action: @{user} summoned a totem.", battle=True)
                continue
    
            if action_name == "spawn_pet":
                self._log_event(f"Action: @{user} summoned a companion pet.", battle=True)
                continue
    
            if action_name == "kid":
                self._log_event(f"Action: @{user} summoned Kid.", battle=True)
                continue
    
            if action_name == "franklin":
                self._log_event(f"Action: @{user} summoned Franklin.", battle=True)
                continue
    
            if action_name == "barbarian_shout":
                session["barbarian_shout_rounds_remaining"] = BARBARIAN_SHOUT_DURATION_TURNS
                self._log_event(
                    f"Shout: @{user} increased party damage by 10% for {BARBARIAN_SHOUT_DURATION_TURNS} turns.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸ—£ï¸ @{user} roars with SHOUT! Party damage +10% for {BARBARIAN_SHOUT_DURATION_TURNS} turns."
                )
                continue
    
            if action_name == "cleave":
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                if not alive_monsters:
                    continue
    
                actual_damage, did_crit = self._calculate_damage_with_scaling(
                    int(action.get("damage", BARBARIAN_CLEAVE_BASE_DAMAGE)),
                    user_data,
                    session,
                    include_crit_meta=True,
                )
                actual_damage = max(1, int(actual_damage))
                indirect_damage = max(1, int(actual_damage * BARBARIAN_CLEAVE_INDIRECT_MULTIPLIER))
    
                direct_targets = []
                preferred_target = self._get_monster_by_index(session, target_index) if target_index else None
                if preferred_target and preferred_target.get("alive"):
                    direct_targets.append(preferred_target)
    
                remaining_for_direct = sorted(
                    [m for m in alive_monsters if m not in direct_targets],
                    key=lambda m: int(m.get("hp", 0)),
                )
                direct_targets.extend(
                    remaining_for_direct[: max(0, BARBARIAN_CLEAVE_DIRECT_TARGETS - len(direct_targets))]
                )
    
                indirect_pool = [m for m in alive_monsters if m not in direct_targets]
                indirect_targets = sorted(indirect_pool, key=lambda m: int(m.get("hp", 0)))[:BARBARIAN_CLEAVE_INDIRECT_TARGETS]
    
                total_dealt = 0
                defeated = 0
    
                for target_monster in direct_targets:
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(actual_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - actual_damage)
                    total_dealt += dealt
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        defeated += 1
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(session, user, int(target_monster.get("level", 1)))
    
                for target_monster in indirect_targets:
                    if not target_monster.get("alive"):
                        continue
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(indirect_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - indirect_damage)
                    total_dealt += dealt
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        defeated += 1
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(session, user, int(target_monster.get("level", 1)))
    
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_dealt
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_dealt
    
                crit_text = " (CRIT)" if did_crit else ""
                self._log_event(
                    f"Cleave: @{user} hit {len(direct_targets)} direct and {len(indirect_targets)} indirect targets for {total_dealt} total{crit_text}.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸª“ @{user} cleaves {len(direct_targets)} direct and {len(indirect_targets)} indirect enemies for {total_dealt} total damage{crit_text}!"
                )
                if defeated > 0:
                    await self._send_battle_message(f"@{user}'s cleave dropped {defeated} enemy(ies)!")
                continue
    
            if action_name == "whirlwind":
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                if not alive_monsters:
                    continue
    
                whirlwind_damage, did_crit = self._calculate_damage_with_scaling(
                    int(action.get("damage", BARBARIAN_WHIRLWIND_BASE_DAMAGE)),
                    user_data,
                    session,
                    include_crit_meta=True,
                )
                whirlwind_damage = max(1, int(whirlwind_damage))
    
                total_dealt = 0
                defeated = 0
                bleed_applied = 0
                for target_monster in alive_monsters:
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(whirlwind_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - whirlwind_damage)
                    total_dealt += dealt
    
                    if target_monster.get("alive") and random.random() < BARBARIAN_WHIRLWIND_BLEED_CHANCE:
                        target_monster["bleed_stacks"] = int(target_monster.get("bleed_stacks", 0)) + 1
                        target_monster["bleed_rounds_remaining"] = max(
                            int(target_monster.get("bleed_rounds_remaining", 0)),
                            BLEED_DURATION,
                        )
                        bleed_applied += 1
    
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        defeated += 1
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(session, user, int(target_monster.get("level", 1)))
    
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_dealt
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_dealt
                user_data["barbarian_whirlwind_cooldown"] = BARBARIAN_WHIRLWIND_COOLDOWN_TURNS
    
                crit_text = " (CRIT)" if did_crit else ""
                self._log_event(
                    f"Whirlwind: @{user} hit {len(alive_monsters)} enemies for {total_dealt} total{crit_text}; bleed on {bleed_applied}.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸŒ€ @{user} spins WHIRLWIND for {total_dealt} total damage across {len(alive_monsters)} enemies{crit_text}!"
                )
                if bleed_applied > 0:
                    await self._send_battle_message(f"ðŸ©¸ Whirlwind applied bleed to {bleed_applied} enemy(ies).")
                if defeated > 0:
                    await self._send_battle_message(f"@{user}'s whirlwind dropped {defeated} enemy(ies)!")
                continue
    
            if action_name == "jdam":
                if target_index:
                    primary = self._get_monster_by_index(session, target_index)
                else:
                    primary = self._get_active_monster(session)
                if not primary:
                    continue
    
                jdam_damage, did_crit = self._calculate_damage_with_scaling(
                    int(action.get("damage", BUFF_JDAM_BASE_DAMAGE)),
                    user_data,
                    session,
                    include_crit_meta=True,
                )
    
                crit_charges = int(user_data.get("buff_jdam_forced_crit_charges", 0))
                used_forced_crit = False
                if crit_charges > 0 and not did_crit:
                    jdam_damage = max(1, int(jdam_damage * CRIT_MULTIPLIER))
                    did_crit = True
                    used_forced_crit = True
                elif (not did_crit) and bool(user_data.get("buff_franklin_crit_triggered")):
                    if random.random() < BUFF_FRANKLIN_JDAM_CRIT_CHANCE_BONUS:
                        jdam_damage = max(1, int(jdam_damage * CRIT_MULTIPLIER))
                        did_crit = True
                if used_forced_crit:
                    user_data["buff_jdam_forced_crit_charges"] = max(0, crit_charges - 1)
                if did_crit:
                    user_data["buff_jdam_crit_triggered"] = True
    
                jdam_damage = max(1, int(jdam_damage))
                splash_damage = max(1, jdam_damage // 2)
    
                total_dealt = 0
                impacted = []
    
                hp_before = int(primary.get("hp", 0))
                dealt_primary = min(jdam_damage, hp_before)
                primary["hp"] = max(0, hp_before - jdam_damage)
                total_dealt += dealt_primary
                impacted.append(primary)
    
                secondary_candidates = [
                    m for m in session.get("monsters", [])
                    if m.get("alive") and m.get("id") != primary.get("id")
                ]
                secondary_targets = random.sample(secondary_candidates, k=min(2, len(secondary_candidates)))
                for secondary in secondary_targets:
                    hp_before = int(secondary.get("hp", 0))
                    dealt = min(splash_damage, hp_before)
                    secondary["hp"] = max(0, hp_before - splash_damage)
                    total_dealt += dealt
                    impacted.append(secondary)
    
                for enemy in impacted:
                    if enemy.get("hp", 0) > 0 or not enemy.get("alive"):
                        continue
                    enemy["alive"] = False
                    enemy["killed_by"] = user
                    user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                    user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                    if enemy.get("is_loot_goblin"):
                        await self._award_loot_goblin_rewards(
                            session,
                            user,
                            int(enemy.get("level", 1)),
                        )
    
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_dealt
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_dealt
    
                crit_text = " (CRIT)" if did_crit else ""
                buff_text = " [Franklin buff consumed]" if used_forced_crit else ""
                self._log_event(
                    f"JDAM: @{user} dealt {dealt_primary} to primary + splash {splash_damage} to {len(secondary_targets)} targets ({total_dealt} total).",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸŽ¯ @{user} drops JDAM for {total_dealt} total damage{crit_text}{buff_text} (primary + 2 at half damage)."
                )
                continue
    
            if action_name == "nuke":
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                if not alive_monsters:
                    continue
                total_dealt = 0
                defeated = 0
                for target_monster in alive_monsters:
                    max_hp = int(target_monster.get("max_hp", max(1, int(target_monster.get("hp", 1)))))
                    nuke_damage = max(1, int(max_hp * BUFF_NUKE_HP_PERCENT))
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(nuke_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - nuke_damage)
                    total_dealt += dealt
    
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        defeated += 1
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(
                                session,
                                user,
                                int(target_monster.get("level", 1)),
                            )
    
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + int(total_dealt)
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + int(total_dealt)
                user_data["buff_kid_intercept_triggered"] = False
                user_data["buff_franklin_crit_triggered"] = False
                user_data["buff_franklin_jdam_buff_triggered"] = False
                user_data["buff_jdam_crit_triggered"] = False
                user_data["buff_jdam_forced_crit_charges"] = 0
    
                self._log_event(
                    f"NUKE: @{user} dealt {total_dealt} total damage to all enemies ({defeated} defeated).",
                    battle=True,
                )
                await self._send_battle_message(
                    f"â˜¢ï¸ @{user} launches NUKE! All enemies take 90% of max HP ({defeated} defeated)."
                )
                continue
    
            # Process streamer gamba - chance-based AoE with occasional self-backfire
            if action_name == "gamba":
                streamer_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                gamba_damage = 3 + max(0, streamer_level - 1)
                gamba_damage = max(1, int(gamba_damage * self._get_donut_effectiveness_multiplier(session)))
                hit_chance = min(
                    GAMBA_MAX_HIT_CHANCE,
                    GAMBA_BASE_HIT_CHANCE + ((streamer_level - 1) * GAMBA_HIT_CHANCE_PER_LEVEL),
                )
    
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                hits = 0
                total_damage = 0
                for target_monster in alive_monsters:
                    if random.random() >= hit_chance:
                        continue
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(gamba_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - gamba_damage)
                    hits += 1
                    total_damage += dealt
    
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        self._log_event(f"Monster down: {target_monster.get('name')} defeated by @{user}.", battle=True)
    
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_damage
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_damage
    
                backfire_chance = max(
                    GAMBA_MIN_BACKFIRE_CHANCE,
                    GAMBA_BASE_BACKFIRE_CHANCE - ((streamer_level - 1) * GAMBA_BACKFIRE_REDUCTION_PER_LEVEL),
                )
                backfired = random.random() < backfire_chance
                self_damage = 0
                if backfired:
                    self_damage = GAMBA_SELF_DAMAGE_BASE + ((streamer_level - 1) // GAMBA_SELF_DAMAGE_LEVEL_STEP)
                    current_hp = int(user_data.get("hp_current", DEFAULT_PLAYER_HP))
                    new_hp = max(0, current_hp - self_damage)
                    actual_self_damage = current_hp - new_hp
                    user_data["hp_current"] = new_hp
                    if current_hp > 0 and new_hp <= 0:
                        user_data["times_knocked_out"] = int(user_data.get("times_knocked_out", 0)) + 1
                        despawned = self._despawn_buff_pets_for_owner(session, user)
                        if despawned:
                            await self._send_battle_message(
                                f"ðŸ’¨ {', '.join(despawned)} vanish as @{user} is knocked out!"
                            )
                    self_damage = actual_self_damage
    
                self._log_event(
                    f"Gamba: @{user} hit {hits}/{len(alive_monsters)} enemies for {gamba_damage} each"
                    + (f" and took {self_damage} backfire damage." if backfired else "."),
                    battle=True,
                )
                if backfired:
                    await self._send_battle_message(
                        f"ðŸŽ² @{user} gamba hit {hits}/{len(alive_monsters)} enemies for {gamba_damage} each, but took {self_damage} backfire damage!"
                    )
                else:
                    await self._send_battle_message(
                        f"ðŸŽ² @{user} gamba hit {hits}/{len(alive_monsters)} enemies for {gamba_damage} each!"
                    )
                continue
            
            # Process warlock summon_imp - already created in command, just log it
            if action_name == "summon_imp":
                self._log_event(f"Action: @{user} summoned an imp.", battle=True)
                continue
    
            if action_name == "summon_undead":
                self._log_event(f"Action: @{user} commanded undead summons.", battle=True)
                continue
    
            # Process Hop greenarrow - already created in command, just log it
            if action_name == "greenarrow":
                self._log_event(f"Action: @{user} summoned green arrows.", battle=True)
                continue
    
            # Process warlock summon_dragon - already created in command, just log it
            if action_name == "summon_dragon":
                self._log_event(f"Action: @{user} summoned a dragon.", battle=True)
                continue
            
            # Process streamer rez - resurrect knocked out party member
            if action_name == "rez":
                rez_target = action.get("rez_target")
                if rez_target:
                    target_data = self.state.get_user(rez_target)
                    max_hp = int(target_data.get("hp_max", DEFAULT_PLAYER_HP))
                    rez_hp = max_hp // 2  # Half health
                    target_data["hp_current"] = rez_hp
                    self._log_event(f"Action: @{user} resurrected @{rez_target} with {rez_hp} HP.", battle=True)
                    await self._send_battle_message(f"@{user} resurrected @{rez_target} with {rez_hp} HP!")
                continue
            
            # Collect heal actions to process after monster attacks
            if action_name == "heal":
                heal_actions.append(action)
                continue
            
            # Process c4 - AoE damage to all monsters with hit chance
            if action_name == "c4":
                user_data = self.state.get_user(user)
                hop_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                base_damage = HOP_C4_BASE_DAMAGE + (hop_level - 1) * BASE_DAMAGE_BONUS_PER_LEVEL
                base_damage = max(1, int(base_damage * self._get_donut_effectiveness_multiplier(session)))
                
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                hits = 0
                total_damage = 0
                for monster in alive_monsters:
                    if random.random() < HOP_C4_HIT_CHANCE:
                        hp_before = int(monster.get("hp", 0))
                        dealt = min(base_damage, hp_before)
                        monster["hp"] = max(0, hp_before - base_damage)
                        hits += 1
                        total_damage += dealt
                        if monster.get("hp", 0) <= 0 and monster.get("alive"):
                            monster["alive"] = False
                            monster["killed_by"] = user
                            user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                            user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                            self._log_event(f"Monster down: {monster.get('name')} defeated by @{user}.", battle=True)
                
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_damage
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_damage
                
                self._log_event(f"C4: @{user} threw C4 hitting {hits}/{len(alive_monsters)} targets for {base_damage} each.", battle=True)
                await self._send_battle_message(f"ðŸ’£ @{user} threw C4! Hit {hits}/{len(alive_monsters)} targets for {base_damage} damage each!")
                continue
    
            if action_name == "teargass":
                deputy_user = self.state.get_user(user)
                alive_monsters = sorted(
                    [m for m in session.get("monsters", []) if m.get("alive")],
                    key=lambda m: int(m.get("index", 0)),
                )
                chance = DEPUTY_TEARGASS_START_CHANCE
                stunned_count = 0
                for target_monster in alive_monsters:
                    roll = random.random()
                    if roll <= chance:
                        target_monster["stun_turns_remaining"] = 1
                        stunned_count += 1
                    chance = max(0.05, chance * DEPUTY_TEARGASS_DECAY)
    
                deputy_user["deputy_teargass_cooldown"] = DEPUTY_TEARGASS_COOLDOWN_TURNS
                self._log_event(
                    f"Teargass: @{user} stunned {stunned_count}/{len(alive_monsters)} enemies.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸš¨ @{user} deployed TEARGASS! {stunned_count}/{len(alive_monsters)} enemies are stunned for 1 turn."
                )
                continue
    
            if action_name == "donut":
                deputy_user = self.state.get_user(user)
                session["deputy_donut_rounds_remaining"] = DEPUTY_DONUT_DURATION_TURNS
                deputy_user["deputy_donut_cooldown"] = DEPUTY_DONUT_COOLDOWN_TURNS
                self._log_event(
                    f"Donut: @{user} granted party +10% effectiveness for {DEPUTY_DONUT_DURATION_TURNS} turns.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸ© @{user} served donuts! Party effectiveness increased by 10% for {DEPUTY_DONUT_DURATION_TURNS} turns."
                )
                continue
    
            if action_name == "brew":
                alchemist_user = self.state.get_user(user)
                alchemist_level = self._get_level_from_xp(int(alchemist_user.get("xp", 0)), alchemist_user)
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                ally_candidates = [
                    name for name in session.get("participants", [])
                    if name != user and int(self.state.get_user(name).get("hp_current", 0)) > 0
                ]
    
                do_buff = random.random() < ALCHEMIST_BREW_BUFF_CHANCE
                if do_buff and ally_candidates:
                    if len(ally_candidates) >= 3:
                        ally_count = random.randint(3, len(ally_candidates))
                    else:
                        ally_count = len(ally_candidates)
                    chosen_allies = random.sample(ally_candidates, ally_count)
                    buff_type = random.choice(["hp", "damage", "crit"])
    
                    if buff_type == "hp":
                        heal_amount = ALCHEMIST_BREW_HP_BASE + max(0, (alchemist_level - 1) // 2)
                        total_healed = 0
                        for ally_name in chosen_allies:
                            ally = self.state.get_user(ally_name)
                            hp_now = int(ally.get("hp_current", 0))
                            hp_max = int(ally.get("hp_max", DEFAULT_PLAYER_HP))
                            healed = min(heal_amount, max(0, hp_max - hp_now))
                            if healed <= 0:
                                continue
                            ally["hp_current"] = hp_now + healed
                            total_healed += healed
                        alchemist_user["healing_done"] = int(alchemist_user.get("healing_done", 0)) + total_healed
                        self._log_event(
                            f"Brew: @{user} restored {total_healed} HP across {len(chosen_allies)} allies.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"ðŸ§ª @{user} brewed a vitality tonic! {len(chosen_allies)} allies healed for {total_healed} total HP."
                        )
                    elif buff_type == "damage":
                        damage_bonus = ALCHEMIST_BREW_DAMAGE_BASE + max(0, (alchemist_level - 1) // 4)
                        for ally_name in chosen_allies:
                            ally = self.state.get_user(ally_name)
                            ally["alchemist_brew_damage_bonus"] = int(ally.get("alchemist_brew_damage_bonus", 0)) + damage_bonus
                        self._log_event(
                            f"Brew: @{user} granted +{damage_bonus} damage to {len(chosen_allies)} allies.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"ðŸ§ª @{user} brewed a fury tonic! {len(chosen_allies)} allies gain +{damage_bonus} damage for this battle."
                        )
                    else:
                        crit_bonus = ALCHEMIST_BREW_CRIT_BASE + (max(0, alchemist_level - 1) * 0.003)
                        for ally_name in chosen_allies:
                            ally = self.state.get_user(ally_name)
                            ally["alchemist_brew_crit_bonus"] = min(
                                0.40,
                                float(ally.get("alchemist_brew_crit_bonus", 0.0)) + crit_bonus,
                            )
                        crit_percent = int(round(crit_bonus * 100))
                        self._log_event(
                            f"Brew: @{user} granted +{crit_percent}% crit to {len(chosen_allies)} allies.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"ðŸ§ª @{user} brewed a focus tonic! {len(chosen_allies)} allies gain +{crit_percent}% crit chance for this battle."
                        )
                elif alive_monsters:
                    applied = 0
                    for target_monster in alive_monsters:
                        previous = int(target_monster.get("drunk_turns_remaining", 0))
                        target_monster["drunk_turns_remaining"] = max(previous, 1)
                        applied += 1
                    self._log_event(
                        f"Brew: @{user} intoxicated {applied} enemy(ies).",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"ðŸ» @{user} spiked the enemy drinks! {applied} enemy(ies) are DRUNK and will become HUNGOVER next turn."
                    )
                else:
                    self._log_event(f"Brew: @{user} had no valid brew targets.", battle=True)
                    await self._send_battle_message(f"@{user}'s brew fizzles with no valid targets.")
                continue
    
            if action_name == "bottle":
                alchemist_user = self.state.get_user(user)
                if target_index:
                    monster = self._get_monster_by_index(session, target_index)
                else:
                    monster = self._get_active_monster(session)
                if not monster:
                    continue
    
                bottle_damage, did_crit = self._calculate_damage_with_scaling(
                    int(action.get("damage", ALCHEMIST_BOTTLE_BASE_DAMAGE)),
                    alchemist_user,
                    session,
                    include_crit_meta=True,
                )
                bottle_damage = max(1, int(bottle_damage))
                if not did_crit and random.random() < ALCHEMIST_BOTTLE_BONUS_CRIT_CHANCE:
                    bottle_damage = max(1, int(bottle_damage * CRIT_MULTIPLIER))
                    did_crit = True
    
                hp_before = int(monster.get("hp", 0))
                dealt = min(bottle_damage, hp_before)
                monster["hp"] = max(0, hp_before - bottle_damage)
                total_dealt = dealt
    
                inflicted_bleed = False
                if monster.get("alive") and random.random() < ALCHEMIST_BOTTLE_BLEED_CHANCE:
                    monster["bleed_stacks"] = int(monster.get("bleed_stacks", 0)) + 1
                    monster["bleed_rounds_remaining"] = max(
                        int(monster.get("bleed_rounds_remaining", 0)),
                        ALCHEMIST_BOTTLE_BLEED_DURATION,
                    )
                    inflicted_bleed = True
    
                if monster.get("hp", 0) <= 0 and monster.get("alive"):
                    monster["alive"] = False
                    monster["killed_by"] = user
                    alchemist_user["monsters_killed"] = int(alchemist_user.get("monsters_killed", 0)) + 1
                    alchemist_user["killing_blows"] = int(alchemist_user.get("killing_blows", 0)) + 1
                    if monster.get("is_loot_goblin"):
                        await self._award_loot_goblin_rewards(session, user, int(monster.get("level", 1)))
    
                remaining_targets = [
                    m for m in session.get("monsters", [])
                    if m.get("alive") and m.get("id") != monster.get("id")
                ]
                shard_count = random.randint(0, ALCHEMIST_BOTTLE_SHARD_MAX)
                actual_shard_targets = random.sample(remaining_targets, min(shard_count, len(remaining_targets)))
                shard_bleeds = 0
                for shard_target in actual_shard_targets:
                    shard_hp_before = int(shard_target.get("hp", 0))
                    shard_dealt = min(ALCHEMIST_BOTTLE_SHARD_DAMAGE, shard_hp_before)
                    shard_target["hp"] = max(0, shard_hp_before - ALCHEMIST_BOTTLE_SHARD_DAMAGE)
                    total_dealt += shard_dealt
                    shard_target["bleed_stacks"] = int(shard_target.get("bleed_stacks", 0)) + 1
                    shard_target["bleed_rounds_remaining"] = max(
                        int(shard_target.get("bleed_rounds_remaining", 0)),
                        ALCHEMIST_BOTTLE_BLEED_DURATION,
                    )
                    shard_bleeds += 1
                    if shard_target.get("hp", 0) <= 0 and shard_target.get("alive"):
                        shard_target["alive"] = False
                        shard_target["killed_by"] = user
                        alchemist_user["monsters_killed"] = int(alchemist_user.get("monsters_killed", 0)) + 1
                        alchemist_user["killing_blows"] = int(alchemist_user.get("killing_blows", 0)) + 1
                        if shard_target.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(session, user, int(shard_target.get("level", 1)))
    
                alchemist_user["lifetime_monster_damage"] = int(alchemist_user.get("lifetime_monster_damage", 0)) + total_dealt
                alchemist_user["damage_done"] = int(alchemist_user.get("damage_done", 0)) + total_dealt
    
                crit_text = " CRIT!" if did_crit else ""
                bleed_text = " Bleed applied!" if inflicted_bleed else ""
                shard_text = f" {shard_bleeds} shard bleed hit(s)." if shard_bleeds > 0 else ""
                self._log_event(
                    f"Bottle: @{user} dealt {total_dealt} total damage.{crit_text}{bleed_text}{shard_text}",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸ¾ @{user} smashes a bottle for {total_dealt} total damage.{crit_text}{bleed_text}{shard_text}"
                )
                continue
    
            if action_name == "revenant_doom":
                revenant_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                doom_damage = REVENANT_DOOM_BASE_DAMAGE + (
                    max(0, revenant_level - 1) * REVENANT_DOOM_DAMAGE_PER_LEVEL
                )
                doom_damage = max(
                    1,
                    int(doom_damage * self._get_donut_effectiveness_multiplier(session)),
                )
    
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                eligible_targets = [
                    m for m in alive_monsters
                    if self._monster_has_revenant_doom_status(m)
                ]
    
                total_dealt = 0
                hits = 0
                defeated = 0
                for target_monster in eligible_targets:
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(doom_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - doom_damage)
                    target_monster["berzerk_turns_remaining"] = max(
                        int(target_monster.get("berzerk_turns_remaining", 0)),
                        REVENANT_BERZERK_DURATION_TURNS,
                    )
                    total_dealt += dealt
                    hits += 1
    
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        defeated += 1
                        self._log_event(
                            f"Monster down: {target_monster.get('name')} doomed by @{user}.",
                            battle=True,
                        )
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(
                                session,
                                user,
                                int(target_monster.get("level", 1)),
                            )
    
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_dealt
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_dealt
                user_data["revenant_doom_cooldown"] = REVENANT_DOOM_COOLDOWN_TURNS
    
                if hits > 0:
                    self._log_event(
                        f"Doom: @{user} struck {hits} afflicted enemies for {total_dealt} total damage and induced berzerk.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"â˜ ï¸ @{user} unleashed DOOM on {hits} afflicted enemies for {total_dealt} total damage!"
                    )
                    await self._send_battle_message(
                        f"ðŸ”¥ DOOM applied BERZERK to {hits} enemy(ies) for {REVENANT_BERZERK_DURATION_TURNS} turn(s)."
                    )
                    if defeated > 0:
                        await self._send_battle_message(
                            f"@{user} finished {defeated} enemy(ies) with DOOM."
                        )
                else:
                    self._log_event(
                        f"Doom: @{user} found no enemies with poison, bleed, stun, or berzerk.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"@{user} cast DOOM, but no enemies had poison, bleed, stun, or berzerk."
                    )
                continue
    
            if action_name == "tommygun":
                deputy_user = self.state.get_user(user)
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                if not alive_monsters:
                    continue
    
                hit_count = len(alive_monsters)
                if hit_count <= 0:
                    continue
    
                deputy_level = self._get_level_from_xp(int(deputy_user.get("xp", 0)), deputy_user)
                hit_percent = DEPUTY_TOMMYGUN_HIT_PERCENT_BASE + (
                    max(0, deputy_level - 1) * DEPUTY_TOMMYGUN_HIT_PERCENT_PER_LEVEL
                )
                hit_percent = min(hit_percent, 0.35)
    
                total_dealt = 0
                kills = 0
                hit_details = []
                preferred_target = self._get_monster_by_index(session, target_index) if target_index else None
                target_pool = list(alive_monsters)
                for hit_number in range(hit_count):
                    current_alive = [m for m in target_pool if m.get("alive")]
                    if not current_alive:
                        break
                    if hit_number == 0 and preferred_target and preferred_target.get("alive"):
                        target_monster = preferred_target
                    else:
                        target_monster = random.choice(current_alive)
    
                    target_max_hp = int(target_monster.get("max_hp", 1))
                    scaled_per_hit = int(target_max_hp * hit_percent)
                    minimum_per_hit = DEPUTY_TOMMYGUN_MIN_HIT_DAMAGE + ((max(1, deputy_level) - 1) // 3)
                    per_hit_damage = max(minimum_per_hit, scaled_per_hit)
                    per_hit_damage = max(1, int(per_hit_damage * self._get_donut_effectiveness_multiplier(session)))
    
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(per_hit_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - per_hit_damage)
                    total_dealt += dealt
                    hit_details.append(f"{target_monster.get('name')}:{dealt}")
    
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        deputy_user["monsters_killed"] = int(deputy_user.get("monsters_killed", 0)) + 1
                        deputy_user["killing_blows"] = int(deputy_user.get("killing_blows", 0)) + 1
                        kills += 1
                        self._log_event(f"Monster down: {target_monster.get('name')} defeated by @{user}.", battle=True)
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(
                                session,
                                user,
                                int(target_monster.get("level", 1)),
                            )
    
                deputy_user["lifetime_monster_damage"] = int(deputy_user.get("lifetime_monster_damage", 0)) + total_dealt
                deputy_user["damage_done"] = int(deputy_user.get("damage_done", 0)) + total_dealt
                deputy_user["deputy_tommygun_cooldown"] = DEPUTY_TOMMYGUN_COOLDOWN_TURNS
    
                self._log_event(
                    f"Tommygun: @{user} fired {len(hit_details)} rotating hits across live targets for {total_dealt} total ({kills} kills).",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸ”« @{user} unloads TOMMYGUN! {len(hit_details)} hits across live enemies for {total_dealt} total damage ({kills} kills)."
                )
                continue
            
            # Process meow - Khajiit special skill with random object effects
            if action_name == "meow":
                user_data = self.state.get_user(user)
                item = action.get("item", "mysterious object")
                effect_type = action.get("effect_type", "light")
                damage = int(action.get("damage", 0))
                did_crit = False
                if effect_type in {"light", "moderate", "heavy"}:
                    damage, did_crit = self._calculate_damage_with_scaling(
                        damage,
                        user_data,
                        session,
                        include_crit_meta=True,
                    )
                    damage = max(1, int(damage))
                
                if effect_type in {"enemy_wipe", "party_wipe"}:  # legacy: party_wipe
                    # Heavy lourde - crushes all enemies
                    alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                    if alive_monsters:
                        total_dealt = 0
                        defeated = 0
                        for target_monster in alive_monsters:
                            hp_before = int(target_monster.get("hp", 0))
                            dealt = max(0, hp_before)
                            total_dealt += dealt
                            target_monster["hp"] = 0
                            target_monster["alive"] = False
                            target_monster["killed_by"] = user
                            defeated += 1
                            user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                            user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                            if target_monster.get("is_loot_goblin"):
                                await self._award_loot_goblin_rewards(
                                    session,
                                    user,
                                    int(target_monster.get("level", 1)),
                                )
    
                        user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_dealt
                        user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_dealt
                        self._log_event(
                            f"HEAVY LOURDE: @{user} crushed {defeated} enemy(ies) for {total_dealt} total damage!",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"ðŸ’¥ @{user} knocked off the HEAVY LOURDE! It crushes all enemies ({defeated} defeated)!"
                        )
                    else:
                        self._log_event(f"HEAVY LOURDE: @{user} had no enemies to crush.", battle=True)
                        await self._send_battle_message(f"ðŸ’¥ @{user}'s HEAVY LOURDE hits nothing.")
                    
                elif effect_type == "instakill":
                    # Bowling ball - instant kill one random monster
                    alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                    if alive_monsters:
                        target_monster = random.choice(alive_monsters)
                        hp_before = int(target_monster.get("hp", 0))
                        dealt = max(0, hp_before)
                        target_monster["hp"] = 0
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + dealt
                        user_data["damage_done"] = int(user_data.get("damage_done", 0)) + dealt
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        
                        self._log_event(f"INSTAKILL: @{user}'s {item} destroyed {target_monster.get('name')}!", battle=True)
                        await self._send_battle_message(f"ðŸŽ³ @{user}'s {item} INSTANTLY DESTROYS {target_monster.get('name')}!")
                else:
                    # Light, moderate, or heavy damage to random monster
                    alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                    if alive_monsters:
                        target_monster = random.choice(alive_monsters)
                        hp_before = int(target_monster.get("hp", 0))
                        dealt = min(damage, hp_before)
                        target_monster["hp"] = max(0, hp_before - damage)
                        
                        user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + dealt
                        user_data["damage_done"] = int(user_data.get("damage_done", 0)) + dealt
                        
                        if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                            target_monster["alive"] = False
                            target_monster["killed_by"] = user
                            user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                            user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                            self._log_event(f"Monster down: {target_monster.get('name')} defeated by @{user}'s {item}.", battle=True)
                            crit_text = " (CRITICAL!)" if did_crit else ""
                            await self._send_battle_message(f"ðŸ˜¾ @{user}'s {item} hits {target_monster.get('name')} for {damage} damage{crit_text} and DEFEATS it!")
                        else:
                            self._log_event(f"Meow: @{user}'s {item} hit {target_monster.get('name')} for {damage} damage.", battle=True)
                            crit_text = " (CRITICAL!)" if did_crit else ""
                            await self._send_battle_message(f"ðŸ˜¾ @{user}'s {item} hits {target_monster.get('name')} for {damage} damage{crit_text}!")
                
                continue
    
            if action_name == "crack":
                user_data = self.state.get_user(user)
                effect_type = str(action.get("effect_type", "berzerk")).lower()
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                if not alive_monsters:
                    continue
    
                if effect_type == "overdose":
                    target_monster = random.choice(alive_monsters)
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = max(0, hp_before)
                    target_monster["hp"] = 0
                    if target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + dealt
                        user_data["damage_done"] = int(user_data.get("damage_done", 0)) + dealt
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                    self._log_event(f"Crack overdose: @{user} overloaded {target_monster.get('name')}.", battle=True)
                    await self._send_battle_message(f"ðŸ’Š @{user} triggered OVERDOSE! {target_monster.get('name')} collapses instantly!")
                    continue
    
                total_dealt = 0
                for attacker in list(alive_monsters):
                    if not attacker.get("alive"):
                        continue
                    candidates = [m for m in session.get("monsters", []) if m.get("alive") and m.get("id") != attacker.get("id")]
                    if not candidates:
                        break
                    target_monster = random.choice(candidates)
                    attacker_damage = int(attacker.get("custom_damage", MONSTER_BASE_DAMAGE + (int(attacker.get("level", 1)) - 1) * MONSTER_DAMAGE_PER_LEVEL))
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(attacker_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - attacker_damage)
                    total_dealt += dealt
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        self._log_event(f"Monster down: {target_monster.get('name')} defeated in berzerk chain by @{user}.", battle=True)
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(
                                session,
                                user,
                                int(target_monster.get("level", 1)),
                            )
    
                if total_dealt > 0:
                    user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_dealt
                    user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_dealt
                self._log_event(f"Crack berzerk: @{user} forced enemies to attack each other ({total_dealt} total damage).", battle=True)
                await self._send_battle_message(f"ðŸ’¥ @{user} triggered BERZERK! Enemies turned on each other for {total_dealt} total damage!")
                continue
            
            # Process Archangel pray - gain power and self heal
            if action_name == "pray":
                user_data = self.state.get_user(user)
                power = int(user_data.get("archangel_power", 0))
                user_data["archangel_power"] = power + ARCHANGEL_PRAY_POWER_GAIN
                archangel_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                pray_heal_amount = ARCHANGEL_PRAY_HEAL + max(0, archangel_level - 1)
                
                # Heal self
                current_hp = int(user_data.get("hp_current", DEFAULT_PLAYER_HP))
                max_hp = int(user_data.get("hp_max", DEFAULT_PLAYER_HP))
                new_hp = min(max_hp, current_hp + pray_heal_amount)
                healed = new_hp - current_hp
                user_data["hp_current"] = new_hp
                user_data["healing_done"] = int(user_data.get("healing_done", 0)) + healed
                
                new_power = user_data["archangel_power"]
                self._log_event(f"Pray: @{user} gained {ARCHANGEL_PRAY_POWER_GAIN} power ({new_power} total) and healed {healed} HP.", battle=True)
                await self._send_battle_message(f"ðŸ™ @{user} prays! Power: {new_power} | Healed: {healed} HP")
                continue
            
            # Process Archangel touch - gain power and damage monster
            if action_name == "touch":
                user_data = self.state.get_user(user)
                power = int(user_data.get("archangel_power", 0))
                user_data["archangel_power"] = power + ARCHANGEL_TOUCH_POWER_GAIN
                # Damage is processed normally below, power gain is handled here
                new_power = user_data["archangel_power"]
                self._log_event(f"Touch: @{user} gained {ARCHANGEL_TOUCH_POWER_GAIN} power ({new_power} total).", battle=True)
                # Message will be sent with damage below
            
            # Process Archangel expel - AoE damage and party heal, then reduce power by 2
            if action_name == "expel":
                user_data = self.state.get_user(user)
                power = int(user_data.get("archangel_power", 0))
                level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                
                aoe_damage = int((level / 10) + (power * 2))
                heal_amount = int(((level / 10) * power) + power)
                effectiveness = self._get_donut_effectiveness_multiplier(session)
                aoe_damage = max(1, int(aoe_damage * effectiveness))
                heal_amount = max(1, int(heal_amount * effectiveness))
                
                # Damage all alive monsters
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                total_damage = 0
                for monster in alive_monsters:
                    hp_before = int(monster.get("hp", 0))
                    dealt = min(aoe_damage, hp_before)
                    monster["hp"] = max(0, hp_before - aoe_damage)
                    total_damage += dealt
                    
                    if monster.get("hp", 0) <= 0 and monster.get("alive"):
                        monster["alive"] = False
                        monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        self._log_event(f"Monster down: {monster.get('name')} expelled by @{user}.", battle=True)
                
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_damage
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_damage
                
                # Heal all alive party members
                total_healed = 0
                for participant in session.get("participants", []):
                    participant_data = self.state.get_user(participant)
                    current_hp = int(participant_data.get("hp_current", DEFAULT_PLAYER_HP))
                    if current_hp > 0:  # Only heal alive players
                        max_hp = int(participant_data.get("hp_max", DEFAULT_PLAYER_HP))
                        new_hp = min(max_hp, current_hp + heal_amount)
                        healed = new_hp - current_hp
                        participant_data["hp_current"] = new_hp
                        total_healed += healed
    
                # Heal active summons/pets too
                pet_groups = [
                    ("totems", "hp", "max_hp"),
                    ("green_arrows", "hp", "max_hp"),
                    ("dragons", "hp", "max_hp"),
                    ("undead_pets", "hp", "max_hp"),
                    ("streamer_pets", "hp", "max_hp"),
                    ("buff_pets", "hp", "max_hp"),
                    ("spirit_wells", "hp", "max_hp"),
                ]
                for group_name, hp_key, max_key in pet_groups:
                    for pet in session.get(group_name, []):
                        if not pet.get("alive"):
                            continue
                        current_pet_hp = int(pet.get(hp_key, 0))
                        pet_max_hp = int(pet.get(max_key, current_pet_hp))
                        if current_pet_hp <= 0 or pet_max_hp <= 0:
                            continue
                        new_pet_hp = min(pet_max_hp, current_pet_hp + heal_amount)
                        pet_healed = new_pet_hp - current_pet_hp
                        if pet_healed > 0:
                            pet[hp_key] = new_pet_hp
                            total_healed += pet_healed
                
                user_data["healing_done"] = int(user_data.get("healing_done", 0)) + total_healed
                
                # Reduce power by 2
                user_data["archangel_power"] = max(0, int(user_data.get("archangel_power", 0)) - 2)
                
                self._log_event(f"Expel: @{user} dealt {aoe_damage} to {len(alive_monsters)} enemies and healed party for {total_healed} HP total.", battle=True)
                await self._send_battle_message(
                    f"âœ¨ @{user} EXPELS! {aoe_damage} dmg to all enemies | {total_healed} HP healed | Power now {int(user_data.get('archangel_power', 0))}"
                )
                continue
            
            # Process Archangel judgement - heavy single-target damage, then reset power
            if action_name == "judgement":
                user_data = self.state.get_user(user)
                power = int(user_data.get("archangel_power", 0))
                level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                
                judgement_damage = int((2 * (level * power)) + (5 * power))
                judgement_damage = max(1, int(judgement_damage * self._get_donut_effectiveness_multiplier(session)))
                
                if target_index:
                    monster = self._get_monster_by_index(session, target_index)
                else:
                    monster = self._get_active_monster(session)
                
                if not monster:
                    continue
                
                hp_before = int(monster.get("hp", 0))
                dealt = min(judgement_damage, hp_before)
                monster["hp"] = max(0, hp_before - judgement_damage)
                
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + dealt
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + dealt
                
                if monster.get("hp", 0) <= 0 and monster.get("alive"):
                    monster["alive"] = False
                    monster["killed_by"] = user
                    user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                    user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                    self._log_event(f"Monster down: {monster.get('name')} judged by @{user}.", battle=True)
                
                # Reset power
                user_data["archangel_power"] = 0
                
                self._log_event(f"Judgement: @{user} dealt {judgement_damage} to {monster.get('name')}. Power reset to 0.", battle=True)
                await self._send_battle_message(f"âš–ï¸ @{user} passes JUDGEMENT! {judgement_damage} damage to {monster.get('name')} | Power reset to 0")
                continue
            
            if target_index:
                monster = self._get_monster_by_index(session, target_index)
            else:
                monster = self._get_active_monster(session)
            if not monster:
                break
            
            # Apply any bleed damage at start of action (only for non-heal actions)
            if action_name != "heal":
                bleed_stacks = monster.get("bleed_stacks", 0)
                if bleed_stacks > 0:
                    bleed_total = bleed_stacks * BLEED_DAMAGE
                    monster["hp"] = max(0, monster.get("hp", 0) - bleed_total)
                    self._log_event(f"Bleed: {monster.get('name')} takes {bleed_total} damage from bleed.", battle=True)
                    await self._send_battle_message(f"{monster.get('name')} takes {bleed_total} damage from bleed.")
                    # Decrement bleed round counter
                    monster["bleed_rounds_remaining"] = monster.get("bleed_rounds_remaining", 0) - 1
                    if monster["bleed_rounds_remaining"] <= 0:
                        monster["bleed_stacks"] = 0
                
                # Apply corruption DoT damage
                corruption_damage = monster.get("corruption_damage", 0)
                if corruption_damage > 0:
                    monster["hp"] = max(0, monster.get("hp", 0) - corruption_damage)
                    self._log_event(f"Corruption: {monster.get('name')} takes {corruption_damage} damage from corruption.", battle=True)
                    await self._send_battle_message(f"{monster.get('name')} takes {corruption_damage} damage from corruption.")
                    # Decrement corruption round counter
                    monster["corruption_rounds_remaining"] = monster.get("corruption_rounds_remaining", 0) - 1
                    if monster["corruption_rounds_remaining"] <= 0:
                        monster["corruption_damage"] = 0
    
                # Apply dragon DoT damage
                dragon_damage = monster.get("dragon_dot_damage", 0)
                if dragon_damage > 0:
                    hp_before = int(monster.get("hp", 0))
                    dealt = min(int(dragon_damage), hp_before)
                    monster["hp"] = max(0, hp_before - int(dragon_damage))
                    dragon_owner = str(monster.get("dragon_dot_owner", "")).strip().lower()
                    self._add_pet_owner_damage(dragon_owner, dealt)
                    self._log_event(
                        f"Dragonfire: {monster.get('name')} takes {dealt} damage from dragonfire.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"{monster.get('name')} takes {dealt} damage from dragonfire."
                    )
                    monster["dragon_dot_rounds_remaining"] = monster.get("dragon_dot_rounds_remaining", 0) - 1
                    if monster["dragon_dot_rounds_remaining"] <= 0:
                        monster["dragon_dot_damage"] = 0
                
                # Apply gross_out DoT damage (Khajiit hairball)
                gross_out_damage = monster.get("gross_out_damage", 0)
                if gross_out_damage > 0:
                    monster["hp"] = max(0, monster.get("hp", 0) - gross_out_damage)
                    self._log_event(
                        f"Gross Out: {monster.get('name')} takes {gross_out_damage} damage from being grossed out.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"{monster.get('name')} is grossed out and takes {gross_out_damage} damage!"
                    )
                    monster["gross_out_rounds_remaining"] = monster.get("gross_out_rounds_remaining", 0) - 1
                    if monster["gross_out_rounds_remaining"] <= 0:
                        monster["gross_out_damage"] = 0
    
                # Decrement stun counter
                if monster.get("stun_turns_remaining", 0) > 0:
                    monster["stun_turns_remaining"] = monster.get("stun_turns_remaining", 0) - 1
            
            # Calculate actual damage with level scaling and crit
            actual_damage, did_crit = self._calculate_damage_with_scaling(
                damage,
                user_data,
                session,
                include_crit_meta=True,
            )
    
            if action_name == "reap":
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                if not alive_monsters:
                    continue
                primary_target = monster
                total_damage = 0
                total_hits = 0
                extra_hits = 0
                killed_any = False
                reap_hit_details = []
    
                for target_monster in alive_monsters:
                    if target_monster is primary_target:
                        hit = True
                    else:
                        hit = random.random() < REAP_AOE_HIT_CHANCE
                    if not hit:
                        continue
    
                    hit_damage = actual_damage
                    crit = False
                    instakill = False
                    if random.random() < REAP_CRIT_CHANCE:
                        hit_damage = int(hit_damage * CRIT_MULTIPLIER)
                        crit = True
                    if random.random() < REAP_INSTAKILL_CHANCE:
                        hit_damage = int(target_monster.get("hp", 0))
                        instakill = True
    
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(hit_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - hit_damage)
                    total_damage += dealt
                    total_hits += 1
                    if target_monster is not primary_target:
                        extra_hits += 1
    
                    if instakill:
                        self._log_event(
                            f"Reap: @{user} executed {target_monster.get('name')} instantly.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"@{user} executed {target_monster.get('name')} with Reap!"
                        )
                    elif crit:
                        self._log_event(
                            f"Reap: @{user} crit {target_monster.get('name')} for {hit_damage} damage.",
                            battle=True,
                        )
    
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        killed_any = True
                        self._log_event(
                            f"Monster down: {target_monster.get('name')} defeated by @{user}.",
                            battle=True,
                        )
    
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(
                                session,
                                user,
                                int(target_monster.get("level", 1)),
                            )
    
                    detail_tags = []
                    if crit:
                        detail_tags.append("CRIT")
                    if instakill:
                        detail_tags.append("EXEC")
                    if not target_monster.get("alive"):
                        detail_tags.append("KO")
                    target_label = f"{target_monster.get('name')}#{target_monster.get('index', '?')}"
                    tag_text = f" ({', '.join(detail_tags)})" if detail_tags else ""
                    reap_hit_details.append(f"{target_label} -{dealt}{tag_text}")
    
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_damage
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_damage
    
                self._log_event(
                    f"Action: @{user} used reap for {total_damage} total damage ({total_hits} hits).",
                    battle=True,
                )
                if reap_hit_details:
                    preview_count = 4
                    preview = "; ".join(reap_hit_details[:preview_count])
                    remaining = len(reap_hit_details) - preview_count
                    extra_text = f"; +{remaining} more" if remaining > 0 else ""
                    await self._send_battle_message(
                        f"@{user} reap hits: {preview}{extra_text}. Total {total_damage} over {total_hits} hits."
                    )
                if extra_hits > 0:
                    await self._send_battle_message(
                        f"@{user}'s reap cleaved {extra_hits} additional enemies!"
                    )
    
                if killed_any:
                    usage = user_data.setdefault("stream_usage", {})
                    if not usage.get("revenant_kill_reward"):
                        user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + REVENANT_KILL_GACHA
                        raffle_cog = self._get_raffle_cog()
                        if raffle_cog:
                            raffle_cog.state.add_entries(user, REVENANT_KILL_ENTRIES)
                        usage["revenant_kill_reward"] = True
                        self._log_event(
                            f"Revenant kill reward: @{user} +{REVENANT_KILL_GACHA} gacha tokens, +{REVENANT_KILL_ENTRIES} entries.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"@{user} claimed the revenant kill reward: +{REVENANT_KILL_GACHA} gacha tokens, +{REVENANT_KILL_ENTRIES} entries."
                        )
                continue
    
            if action_name == "goldrpg":
                hop_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                target_monster = monster
    
                primary_hp_before = int(target_monster.get("hp", 0))
                primary_dealt = min(actual_damage, primary_hp_before)
                target_monster["hp"] = max(0, primary_hp_before - actual_damage)
    
                splash_damage = max(1, primary_dealt // 2)
                alive_sorted = sorted(
                    [m for m in session.get("monsters", []) if m.get("alive")],
                    key=lambda m: int(m.get("index", 0)),
                )
                adjacent_targets = []
                try:
                    primary_pos = next(i for i, m in enumerate(alive_sorted) if m.get("id") == target_monster.get("id"))
                    left = primary_pos - 1
                    right = primary_pos + 1
                    if left >= 0:
                        adjacent_targets.append(alive_sorted[left])
                    if right < len(alive_sorted):
                        adjacent_targets.append(alive_sorted[right])
                except StopIteration:
                    adjacent_targets = []
    
                splash_total = 0
                for adj in adjacent_targets:
                    hp_before = int(adj.get("hp", 0))
                    dealt = min(splash_damage, hp_before)
                    adj["hp"] = max(0, hp_before - splash_damage)
                    splash_total += dealt
    
                impacted_targets = [target_monster] + adjacent_targets
                for impacted in impacted_targets:
                    if impacted.get("hp", 0) > 0 or not impacted.get("alive"):
                        continue
                    impacted["alive"] = False
                    impacted["killed_by"] = user
                    user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                    user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                    self._log_event(f"Monster down: {impacted.get('name')} defeated by @{user}.", battle=True)
    
                    if impacted.get("is_loot_goblin"):
                        await self._award_loot_goblin_rewards(
                            session,
                            user,
                            int(impacted.get("level", 1)),
                        )
    
                bleed_damage = 3 + (max(0, hop_level - 1) * BASE_DAMAGE_BONUS_PER_LEVEL)
                for enemy in [m for m in session.get("monsters", []) if m.get("alive")]:
                    enemy["goldrpg_bleed_damage"] = bleed_damage
                    enemy["goldrpg_bleed_rounds_remaining"] = HOP_GOLDRPG_BLEED_DURATION
    
                total_dealt = primary_dealt + splash_total
                user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + total_dealt
                user_data["damage_done"] = int(user_data.get("damage_done", 0)) + total_dealt
                user_data["hop_goldrpg_ready"] = False
    
                self._log_event(
                    f"GoldRPG: @{user} hit {target_monster.get('name')} for {primary_dealt}, splashed {len(adjacent_targets)} target(s) for {splash_damage}, applied bleed {bleed_damage} for {HOP_GOLDRPG_BLEED_DURATION} turns.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸŒŸ @{user} fired GOLDRPG! Primary {primary_dealt}, splash {splash_damage} to adjacent enemies, all enemies bleed for {bleed_damage} ({HOP_GOLDRPG_BLEED_DURATION} turns)."
                )
                continue
            
            # Check for backstab bleed application (scales with rogue level)
            rogue_level = self._get_level_from_xp(int(user_data.get("xp", 0)))
            # Rogue level scales bleed chance: 25% base + 5% per level
            bleed_chance = BLEED_CHANCE + (rogue_level - 1) * 0.05
            bleed_chance = min(bleed_chance, 1.0)  # Cap at 100%
            
            if action_name == "backstab" and random.random() < bleed_chance:
                # Bleed damage scales with level: 2 base + 1 per level
                bleed_stacks = monster.get("bleed_stacks", 0)
                monster["bleed_stacks"] = bleed_stacks + 1
                monster["bleed_rounds_remaining"] = BLEED_DURATION
                self._log_event(f"Bleed applied to {monster.get('name')} (stack {monster['bleed_stacks']}).", battle=True)
                await self._send_battle_message(f"{monster.get('name')} begins bleeding!")
            
            # Check for bolt stun application (scales with mage level)
            if action_name == "bolt":
                mage_level = self._get_level_from_xp(int(user_data.get("xp", 0)))
                # Mage stun chance scales: 20% base + 5% per level
                stun_chance = STUN_BASE_CHANCE + (mage_level - 1) * STUN_CHANCE_PER_LEVEL
                stun_chance = min(stun_chance, 1.0)  # Cap at 100%
                
                if random.random() < stun_chance:
                    monster["stun_turns_remaining"] = STUN_DURATION
                    self._log_event(f"{monster.get('name')} is stunned by {user}'s bolt!", battle=True)
                    await self._send_battle_message(f"{monster.get('name')} is stunned!")
            
            # Check for corruption DoT application (warlock)
            if action_name == "corruption":
                warlock_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                # DoT damage scales with level: 2 base + 1 per level
                dot_damage = WARLOCK_DOT_BASE_DAMAGE + (warlock_level - 1)
                monster["corruption_damage"] = dot_damage
                monster["corruption_rounds_remaining"] = WARLOCK_DOT_DURATION
                self._log_event(f"Corruption applied to {monster.get('name')} ({dot_damage} dmg/turn for {WARLOCK_DOT_DURATION} turns).", battle=True)
                await self._send_battle_message(f"{monster.get('name')} is corrupted by dark magic!")
            
            # Check for sap stun application (Hop class)
            if action_name == "sap":
                hop_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                # Sap stun chance scales: 25% base + 2% per level
                sap_chance = HOP_SAP_BASE_CHANCE + (hop_level - 1) * HOP_SAP_CHANCE_PER_LEVEL
                sap_chance = min(sap_chance, 1.0)  # Cap at 100%
                
                if random.random() < sap_chance:
                    monster["stun_turns_remaining"] = HOP_SAP_STUN_DURATION
                    self._log_event(f"{monster.get('name')} is stunned by {user}'s sap!", battle=True)
                    await self._send_battle_message(f"{monster.get('name')} is sapped and stunned!")
                else:
                    self._log_event(f"{user}'s sap missed {monster.get('name')}.", battle=True)
                    await self._send_battle_message(f"@{user}'s sap missed!")
    
            if action_name == "tazer":
                deputy_level = self._get_level_from_xp(int(user_data.get("xp", 0)), user_data)
                taze_chance = DEPUTY_TAZE_BASE_STUN_CHANCE + (deputy_level - 1) * DEPUTY_TAZE_STUN_PER_LEVEL
                taze_chance = min(DEPUTY_TAZE_MAX_STUN_CHANCE, taze_chance)
                if random.random() < taze_chance:
                    monster["stun_turns_remaining"] = 1
                    self._log_event(f"{monster.get('name')} is stunned by {user}'s tazer!", battle=True)
                    await self._send_battle_message(f"âš¡ {monster.get('name')} is tazered and stunned!")
            
            # Check for deagle heavy damage chance (Hop class)
            if action_name == "deagle":
                if random.random() < HOP_DEAGLE_HEAVY_CHANCE:
                    actual_damage = actual_damage * 2  # Double damage on heavy hit
                    self._log_event(f"Deagle: @{user} landed a HEAVY shot!", battle=True)
                    await self._send_battle_message(f"@{user}'s deagle lands a HEAVY shot!")
            
            # Check for scratch bleed application (Khajiit class)
            if action_name == "scratch" and random.random() < KHAJIIT_SCRATCH_BLEED_CHANCE:
                bleed_stacks = monster.get("bleed_stacks", 0)
                monster["bleed_stacks"] = bleed_stacks + 1
                monster["bleed_rounds_remaining"] = BLEED_DURATION
                self._log_event(f"Bleed applied to {monster.get('name')} (stack {monster['bleed_stacks']}).", battle=True)
                await self._send_battle_message(f"{monster.get('name')} begins bleeding from scratches!")
            
            # Check for hairball gross_out DoT application (Khajiit class)
            if action_name == "hairball" and random.random() < KHAJIIT_HAIRBALL_GROSSOUT_CHANCE:
                monster["gross_out_damage"] = KHAJIIT_GROSSOUT_DAMAGE
                monster["gross_out_rounds_remaining"] = KHAJIIT_GROSSOUT_DURATION
                self._log_event(f"Gross Out applied to {monster.get('name')} ({KHAJIIT_GROSSOUT_DAMAGE} dmg/turn for {KHAJIIT_GROSSOUT_DURATION} turns).", battle=True)
                await self._send_battle_message(f"{monster.get('name')} is grossed out by the hairball!")
            
            hp_before = int(monster.get("hp", 0))
            dealt = min(actual_damage, hp_before)
            monster["hp"] = max(0, hp_before - actual_damage)
            
            # Log damage (show crit if applicable)
            if did_crit:
                self._log_event(f"Action: @{user} used {action_name} for {actual_damage} damage (CRIT!).", battle=True)
                await self._send_battle_message(f"@{user} {action_name} for {actual_damage} damage (CRITICAL!).")
            else:
                self._log_event(f"Action: @{user} used {action_name} for {actual_damage} damage.", battle=True)
    
            if user_data.get("class_name") == "Hop" and did_crit and action_name != "goldrpg":
                if not user_data.get("hop_goldrpg_ready"):
                    user_data["hop_goldrpg_ready"] = True
                    await self._send_battle_message(f"ðŸ’› @{user} unlocked GOLDRPG!")
            
            # Show power gain for Archangel touch
            if action_name == "touch":
                new_power = int(user_data.get("archangel_power", 0))
                await self._send_battle_message(f"ðŸ‘† @{user} touches for {actual_damage} damage! Power: {new_power}")
            
            user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + dealt
            user_data["damage_done"] = int(user_data.get("damage_done", 0)) + dealt
            
            # Announce if Derp Clone can now ascend at threshold
            if (user_data.get("class_name") == "Derp Clone" and 
                int(user_data.get("lifetime_monster_damage", 0)) >= DERP_CLONE_ASCEND_THRESHOLD and
                int(user_data.get("damage_done", 0)) == dealt):
                await self._send_battle_message(f"@{user} has enough damage to ascend! Use !ascend to choose a path.")
            
            if monster.get("hp", 0) <= 0 and monster.get("alive"):
                monster["alive"] = False
                monster["killed_by"] = user
                user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                self._log_event(f"Monster down: {monster.get('name')} defeated by @{user}.", battle=True)
                
                # Check if loot goblin was killed - special rewards
                if monster.get("is_loot_goblin"):
                    await self._award_loot_goblin_rewards(
                        session,
                        user,
                        int(monster.get("level", 1)),
                    )
                
                if user_data.get("is_revenant") and action_name == "harvest":
                    usage = user_data.setdefault("stream_usage", {})
                    if not usage.get("revenant_kill_reward"):
                        user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + REVENANT_KILL_GACHA
                        raffle_cog = self._get_raffle_cog()
                        if raffle_cog:
                            raffle_cog.state.add_entries(user, REVENANT_KILL_ENTRIES)
                        usage["revenant_kill_reward"] = True
                        self._log_event(
                            f"Revenant kill reward: @{user} +{REVENANT_KILL_GACHA} gacha tokens, +{REVENANT_KILL_ENTRIES} entries.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"@{user} claimed the revenant kill reward: +{REVENANT_KILL_GACHA} gacha tokens, +{REVENANT_KILL_ENTRIES} entries."
                        )
                if self._eligible_for_revenant(user, user_data) and random.random() < REVENANT_CHANCE:
                    await self._grant_revenant(user, user_data)
        
        self._cleanup_dead_summoner_pets(session)
    
        # Now let monsters attack
        self._refresh_party_shields_from_totem(session)
        await self._monster_actions()
    
        await self._apply_healing_totem_pulse(session)
        
        # Now process heal actions after monsters have attacked
        for heal_index, action in enumerate(heal_actions):
            if heal_index > 0:
                await self._maybe_action_delay(session)
            user = action.get("user")
            user_data = self.state.get_user(user)
            participants = session.get("participants", [])
            target_party_index = action.get("target_party_index")
            lowest_hp_user = None
            lowest_hp_value = DEFAULT_PLAYER_HP + 1
            
            # Calculate healer's level and heal amount early (needed for both healing and smite fallback)
            healer_level = self._get_level_from_xp(int(user_data.get("xp", 0)))
            heal_amount = 3 + (healer_level - 1) * HEALING_BONUS_PER_LEVEL
            
            # Determine target: specific party member, lowest HP, or none
            if target_party_index is not None:
                # Heal specific party member (only if alive)
                if 0 <= target_party_index < len(participants):
                    target = participants[target_party_index]
                    target_data = self.state.get_user(target)
                    target_hp = int(target_data.get("hp_current", DEFAULT_PLAYER_HP))
                    # Only set as target if they're alive (HP > 0)
                    if target_hp > 0:
                        lowest_hp_user = target
            else:
                # Find all players with lowest HP > 0 (excluding those at max HP)
                candidates = []
                for participant in participants:
                    participant_data = self.state.get_user(participant)
                    current_hp = int(participant_data.get("hp_current", DEFAULT_PLAYER_HP))
                    max_hp = int(participant_data.get("hp_max", DEFAULT_PLAYER_HP))
                    # Only consider alive players (HP > 0) below max HP
                    if current_hp > 0 and current_hp < max_hp:
                        if current_hp < lowest_hp_value:
                            lowest_hp_value = current_hp
                            candidates = [participant]
                        elif current_hp == lowest_hp_value:
                            candidates.append(participant)
                
                # Randomly pick from candidates if multiple have same lowest HP
                if candidates:
                    lowest_hp_user = random.choice(candidates)
            
            if lowest_hp_user:
                # Heal the target player; healing scales with healer's level
                target_data = self.state.get_user(lowest_hp_user)
                max_hp = int(target_data.get("hp_max", DEFAULT_PLAYER_HP))
                current_hp = int(target_data.get("hp_current", DEFAULT_PLAYER_HP))
                
                new_hp = min(max_hp, current_hp + heal_amount)
                target_data["hp_current"] = new_hp
                self._log_event(f"Action: @{user} used heal to restore {new_hp - current_hp} HP to @{lowest_hp_user}.", battle=True)
                await self._send_battle_message(f"@{user} healed @{lowest_hp_user} for {new_hp - current_hp} HP.")
                user_data["healing_done"] = int(user_data.get("healing_done", 0)) + (new_hp - current_hp)
            else:
                # Everyone is at max HP or dead, smite (attack) random monster for half heal damage (rounded down)
                smite_damage = heal_amount // 2
                
                # Apply monk blessing bonus to smite damage
                participants = session.get("participants", [])
                monk_count = sum(1 for participant in participants if self.state.get_user(participant).get("class_name") == "Monk")
                if monk_count > 0:
                    monk_bonus = 0.5 * monk_count
                    smite_damage = int(smite_damage * (1 + monk_bonus))
                
                alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                if alive_monsters:
                    monster = random.choice(alive_monsters)
                    hp_before = int(monster.get("hp", 0))
                    dealt = min(smite_damage, hp_before)
                    monster["hp"] = max(0, hp_before - smite_damage)
                    self._log_event(f"Action: @{user} used heal but party was full, smited {monster.get('name')} for {smite_damage} damage.", battle=True)
                    await self._send_battle_message(f"@{user} tried to heal but party was full! Smited {monster.get('name')} for {smite_damage} damage instead.")
                    user_data["lifetime_monster_damage"] = int(user_data.get("lifetime_monster_damage", 0)) + dealt
                    user_data["damage_done"] = int(user_data.get("damage_done", 0)) + dealt
                    if monster.get("hp", 0) <= 0 and monster.get("alive"):
                        monster["alive"] = False
                        monster["killed_by"] = user
                        user_data["monsters_killed"] = int(user_data.get("monsters_killed", 0)) + 1
                        user_data["killing_blows"] = int(user_data.get("killing_blows", 0)) + 1
                        self._log_event(f"Monster down: {monster.get('name')} defeated by @{user}.", battle=True)
    
        await self._process_archangel_spirit_wells(session)
        
        session["action_queue"] = []
        session["taunted_warriors"] = []
        session["turn_number"] = int(session.get("turn_number", 0)) + 1
        session["action_window_end"] = _now_ts() + ACTION_WINDOW_SECONDS
        self.state.save_state()
        self._broadcast_state()
        if await self._check_party_defeat():
            return
        await self._check_battle_end()
    
    async def _monster_actions(self):
        session = self.state.session()
        participants = session.get("participants", [])
        if not participants:
            return
        
        # Build list of all alive targets (players, totems, summons)
        alive_targets = []
        for username in participants:
            user = self.state.get_user(username)
            if int(user.get("hp_current", DEFAULT_PLAYER_HP)) > 0:
                alive_targets.append({"type": "player", "name": username})
        
        # Add alive totems
        for totem in session.get("totems", []):
            if totem.get("alive"):
                alive_targets.append({"type": "totem", "data": totem})
        
        # Add alive imps
        for imp in session.get("imps", []):
            if imp.get("alive"):
                alive_targets.append({"type": "imp", "data": imp})
    
        # Add alive green arrows
        for arrow in session.get("green_arrows", []):
            if arrow.get("alive"):
                alive_targets.append({"type": "green_arrow", "data": arrow})
    
        # Add alive dragons
        for dragon in session.get("dragons", []):
            if dragon.get("alive"):
                alive_targets.append({"type": "dragon", "data": dragon})
    
        # Add alive revenant undead pets
        for pet in session.get("undead_pets", []):
            if pet.get("alive"):
                alive_targets.append({"type": "undead", "data": pet})
    
        # Add alive streamer pets
        for pet in session.get("streamer_pets", []):
            if pet.get("alive"):
                alive_targets.append({"type": "streamer_pet", "data": pet})
    
        # Add alive buff pets
        for pet in session.get("buff_pets", []):
            if pet.get("alive"):
                alive_targets.append({"type": "buff_pet", "data": pet})
    
        # Add alive spirit wells
        for well in session.get("spirit_wells", []):
            if well.get("alive"):
                alive_targets.append({"type": "spirit_well", "data": well})
        
        if not alive_targets:
            return
    
        # Ghoul poison ticks once per monster phase
        for monster in [m for m in session.get("monsters", []) if m.get("alive")]:
            poison_damage = int(monster.get("ghoul_poison_damage", 0))
            if poison_damage <= 0:
                continue
            hp_before = int(monster.get("hp", 0))
            dealt = min(poison_damage, hp_before)
            monster["hp"] = max(0, hp_before - poison_damage)
            poison_owner = str(monster.get("ghoul_poison_owner", "")).strip().lower()
            self._add_pet_owner_damage(poison_owner, dealt)
            if dealt > 0:
                self._log_event(
                    f"Ghoul poison: {monster.get('name')} takes {dealt} damage.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"{monster.get('name')} takes {dealt} ghoul poison damage."
                )
            monster["ghoul_poison_rounds_remaining"] = int(monster.get("ghoul_poison_rounds_remaining", 0)) - 1
            if int(monster.get("ghoul_poison_rounds_remaining", 0)) <= 0:
                monster["ghoul_poison_damage"] = 0
    
        # GoldRPG bleed ticks once per monster phase (applies to all alive mobs, unblockable)
        for monster in [m for m in session.get("monsters", []) if m.get("alive")]:
            goldrpg_bleed_damage = int(monster.get("goldrpg_bleed_damage", 0))
            goldrpg_rounds = int(monster.get("goldrpg_bleed_rounds_remaining", 0))
            if goldrpg_bleed_damage <= 0 or goldrpg_rounds <= 0:
                continue
            hp_before = int(monster.get("hp", 0))
            dealt = min(goldrpg_bleed_damage, hp_before)
            monster["hp"] = max(0, hp_before - goldrpg_bleed_damage)
            if dealt > 0:
                self._log_event(
                    f"GoldRPG bleed: {monster.get('name')} takes {dealt} damage.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"{monster.get('name')} takes {dealt} damage from GoldRPG bleed."
                )
            monster["goldrpg_bleed_rounds_remaining"] = goldrpg_rounds - 1
            if int(monster.get("goldrpg_bleed_rounds_remaining", 0)) <= 0:
                monster["goldrpg_bleed_damage"] = 0
            if monster.get("hp", 0) <= 0 and monster.get("alive"):
                monster["alive"] = False
    
        # Summoner corruption-like DoT ticks on players once per monster phase
        for username in participants:
            user_data = self.state.get_user(username)
            rounds = int(user_data.get("summoner_dot_rounds_remaining", 0))
            dot_damage = int(user_data.get("summoner_dot_damage", 0))
            if rounds <= 0 or dot_damage <= 0:
                continue
            hp_before = int(user_data.get("hp_current", 0))
            if hp_before <= 0:
                continue
            dealt = min(dot_damage, hp_before)
            user_data["hp_current"] = max(0, hp_before - dot_damage)
            user_data["summoner_dot_rounds_remaining"] = rounds - 1
            if user_data["summoner_dot_rounds_remaining"] <= 0:
                user_data["summoner_dot_damage"] = 0
            self._log_event(
                f"Summoner rot: @{username} takes {dealt} damage.",
                battle=True,
            )
            await self._send_battle_message(
                f"@{username} takes {dealt} damage from summoner corruption."
            )
            if hp_before > 0 and int(user_data.get("hp_current", 0)) <= 0:
                if not await self._trigger_archangel_death_passive(session, username):
                    user_data["times_knocked_out"] = int(user_data.get("times_knocked_out", 0)) + 1
                    despawned = self._despawn_buff_pets_for_owner(session, username)
                    if despawned:
                        await self._send_battle_message(
                            f"ðŸ’¨ {', '.join(despawned)} vanish as @{username} is knocked out!"
                        )
        
        # Check if any warriors taunted - prioritize them for first two attacks
        taunted_warriors = session.get("taunted_warriors", [])
        taunted_warrior_targets = []
        if taunted_warriors:
            for username in taunted_warriors:
                user = self.state.get_user(username)
                if int(user.get("hp_current", DEFAULT_PLAYER_HP)) > 0:
                    taunted_warrior_targets.append({"type": "player", "name": username})
    
        blob_taunt_targets = [
            t for t in alive_targets
            if t.get("type") == "undead" and str(t.get("data", {}).get("pet_type", "")).lower() == "blob"
        ]
        
        first_attack_forced_arrow = True
        for monster_step_index, monster in enumerate(session.get("monsters", [])):
            if monster_step_index > 0:
                await self._maybe_action_delay(session)
            if not monster.get("alive"):
                continue
    
            drunk_turns = int(monster.get("drunk_turns_remaining", 0))
            if drunk_turns > 0:
                monster["drunk_turns_remaining"] = drunk_turns - 1
                if int(monster.get("drunk_turns_remaining", 0)) <= 0 and not monster.get("hungover_active"):
                    monster["hungover_active"] = True
                    self._log_event(
                        f"Drunk: {monster.get('name')} is now HUNGOVER (90% effectiveness).",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"ðŸ¤¢ {monster.get('name')} is now HUNGOVER! Its skills are reduced for the rest of battle."
                    )
    
            monster_effectiveness = (
                ALCHEMIST_HUNGOVER_EFFECTIVENESS
                if monster.get("hungover_active")
                else 1.0
            )
    
            if monster.get("is_summoner_pet"):
                owner_id = str(monster.get("summoned_by") or "")
                owner_alive = any(
                    m.get("alive") and str(m.get("id")) == owner_id
                    for m in session.get("monsters", [])
                )
                if owner_id and not owner_alive:
                    monster["alive"] = False
                    continue
            
            # Skip if monster is a loot goblin (they don't attack)
            if monster.get("is_loot_goblin"):
                continue
    
            # Skip if monster is stunned
            if monster.get("stun_turns_remaining", 0) > 0:
                self._log_event(f"{monster.get('name')} is stunned and cannot act!", battle=True)
                await self._send_battle_message(f"{monster.get('name')} is stunned and cannot act!")
                continue
    
            berzerk_turns = int(monster.get("berzerk_turns_remaining", 0))
            if berzerk_turns > 0:
                base_damage = int(monster.get("custom_damage", MONSTER_BASE_DAMAGE + (int(monster.get("level", 1)) - 1) * MONSTER_DAMAGE_PER_LEVEL))
                frenzy_damage = max(1, int(base_damage * REVENANT_BERZERK_DAMAGE_MULTIPLIER))
                other_targets = [
                    m for m in session.get("monsters", [])
                    if m.get("alive") and m.get("id") != monster.get("id")
                ]
                if other_targets:
                    target_monster = random.choice(other_targets)
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(frenzy_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - frenzy_damage)
                    self._log_event(
                        f"Berzerk: {monster.get('name')} struck {target_monster.get('name')} for {dealt}.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"ðŸ˜µ {monster.get('name')} is berzerk and hits {target_monster.get('name')} for {dealt}!"
                    )
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        target_monster["killed_by"] = "berzerk"
                        self._log_event(
                            f"Berzerk kill: {target_monster.get('name')} fell to allied frenzy.",
                            battle=True,
                        )
                else:
                    self._log_event(f"Berzerk: {monster.get('name')} rages with no valid target.", battle=True)
                monster["berzerk_turns_remaining"] = max(0, berzerk_turns - 1)
                continue
    
            monster_name = monster.get("name", "").lower()
            monster_level = int(monster.get("level", 1))
    
            if monster_name == SUMMONER_NAME:
                active_pets = [
                    m for m in session.get("monsters", [])
                    if m.get("alive") and m.get("summoned_by") == monster.get("id")
                ]
                pet_cap = 1 + max(0, (monster_level - 1) // 10)
                should_summon = len(active_pets) < pet_cap and (
                    len(active_pets) == 0 or random.random() < 0.55
                )
    
                if should_summon:
                    summon_name = self._choose_summoner_pet_type(session, active_pets)
                    summon_index = len(session.get("monsters", [])) + 1
                    summon_pet = self._build_monster_entry(summon_name, monster_level, summon_index)
                    summon_pet["summoned_by"] = monster.get("id")
                    summon_pet["is_summoner_pet"] = True
                    session.setdefault("monsters", []).append(summon_pet)
                    self._log_event(
                        f"Summoner: {monster.get('name')} summoned {summon_name} ({len(active_pets)+1}/{pet_cap}).",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"{monster.get('name')} summons a {summon_name}!"
                    )
                    continue
    
                candidates = [
                    name for name in participants
                    if int(self.state.get_user(name).get("hp_current", DEFAULT_PLAYER_HP)) > 0
                ]
                if candidates:
                    target_name = random.choice(candidates)
                    target_user = self.state.get_user(target_name)
                    dot_damage = max(1, int((3 + max(0, monster_level - 1)) * monster_effectiveness))
                    target_user["summoner_dot_damage"] = max(dot_damage, int(target_user.get("summoner_dot_damage", 0)))
                    target_user["summoner_dot_rounds_remaining"] = SUMMONER_DOT_DURATION
                    self._log_event(
                        f"Summoner corruption: {monster.get('name')} hexed @{target_name} ({dot_damage}/turn for {SUMMONER_DOT_DURATION} turns).",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"{monster.get('name')} corrupts @{target_name} for {dot_damage} damage over time!"
                    )
                    continue
    
            effective_hex_chance = min(TRICKSTER_HEX_CHANCE, 0.20)
            if monster_name == TRICKSTER_NAME and random.random() < effective_hex_chance:
                candidates = [
                    name for name in participants
                    if int(self.state.get_user(name).get("hp_current", DEFAULT_PLAYER_HP)) > 0
                ]
                if candidates:
                    target_name = random.choice(candidates)
                    target_user = self.state.get_user(target_name)
                    target_user["hexed_turns_remaining"] = 1
                    self._log_event(
                        f"Trickster hex: @{target_name} will be forced to strike an ally next turn.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"Trickster hexed @{target_name}! Their next action is twisted."
                    )
                    continue
    
            if monster_name == SHAMAN_NAME and random.random() < SHAMAN_HEAL_CHANCE:
                heal_targets = [m for m in session.get("monsters", []) if m.get("alive")]
                if heal_targets:
                    target_monster = random.choice(heal_targets)
                    heal_amount = max(1, int((SHAMAN_HEAL_BASE + max(0, monster_level - 1)) * monster_effectiveness))
                    hp_before = int(target_monster.get("hp", 0))
                    max_hp = int(target_monster.get("max_hp", hp_before))
                    target_monster["hp"] = min(max_hp, hp_before + heal_amount)
                    self._log_event(
                        f"Shaman heal: {monster.get('name')} restored {heal_amount} HP to {target_monster.get('name')}",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"{monster.get('name')} healed {target_monster.get('name')} for {heal_amount} HP!"
                    )
                    continue
    
            if monster_name == SKELEPRIEST_NAME and random.random() < 0.5:
                heal_targets = [m for m in session.get("monsters", []) if m.get("alive")]
                if heal_targets:
                    target_monster = random.choice(heal_targets)
                    heal_amount = max(1, int(max(1, (3 + max(0, monster_level - 1)) // 2) * monster_effectiveness))
                    hp_before = int(target_monster.get("hp", 0))
                    max_hp = int(target_monster.get("max_hp", hp_before))
                    target_monster["hp"] = min(max_hp, hp_before + heal_amount)
                    self._log_event(
                        f"Skelepriest heal: {monster.get('name')} restored {heal_amount} HP to {target_monster.get('name')}",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"{monster.get('name')} heals {target_monster.get('name')} for {heal_amount} HP!"
                    )
                    continue
    
            if monster_name == SKELEMAGE_NAME and random.random() < 0.45:
                candidates = [
                    name for name in participants
                    if int(self.state.get_user(name).get("hp_current", DEFAULT_PLAYER_HP)) > 0
                ]
                if candidates:
                    target_name = random.choice(candidates)
                    target_user = self.state.get_user(target_name)
                    dot_damage = max(1, int(max(1, (3 + max(0, monster_level - 1)) // 2) * monster_effectiveness))
                    target_user["summoner_dot_damage"] = max(dot_damage, int(target_user.get("summoner_dot_damage", 0)))
                    target_user["summoner_dot_rounds_remaining"] = SUMMONER_DOT_DURATION
                    self._log_event(
                        f"Skelemage rot: {monster.get('name')} afflicted @{target_name} ({dot_damage}/turn).",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"{monster.get('name')} afflicts @{target_name} with a weak corruption!"
                    )
                    continue
            
            # Pick target - first attack always hits a green arrow if any
            alive_green_arrows = [t for t in alive_targets if t.get("type") == "green_arrow"]
            if first_attack_forced_arrow and alive_green_arrows:
                target = random.choice(alive_green_arrows)
                first_attack_forced_arrow = False
            elif blob_taunt_targets:
                target = random.choice(blob_taunt_targets)
            # Otherwise, prioritize taunted warriors for first 2 attacks if any
            elif taunted_warrior_targets and len(taunted_warrior_targets) > 0:
                target = random.choice(taunted_warrior_targets)
                taunted_warrior_targets.pop(0)  # Remove after use
            else:
                target = random.choice(alive_targets)
            
            damage = int(monster.get("custom_damage", MONSTER_BASE_DAMAGE + (int(monster.get("level", 1)) - 1) * MONSTER_DAMAGE_PER_LEVEL))
            if monster_name in {TRICKSTER_NAME, SHAMAN_NAME}:
                damage = max(1, damage - 1)
            if monster_name == SKELEROG_NAME and random.random() < 0.25:
                damage = int(damage * CRIT_MULTIPLIER)
            damage = max(1, int(damage * monster_effectiveness))
            monster_index = monster.get("index", "?")
            
            if target["type"] == "totem":
                # Attack totem
                totem_data = target["data"]
                if totem_data.get("totem_shield_available"):
                    totem_data["totem_shield_available"] = False
                    owner = totem_data.get("owner", "?")
                    self._log_event(f"Shield Totem: prevented damage to @{owner}'s totem.", battle=True)
                    await self._send_battle_message(f"ðŸ›¡ï¸ Shield Totem blocks the hit on @{owner}'s totem!")
                    continue
                totem_data["hp"] = max(0, totem_data["hp"] - damage)
                if totem_data["hp"] <= 0:
                    totem_data["alive"] = False
                    owner = totem_data.get("owner", "?")
                    self._log_event(f"Monster: {monster.get('name')} destroyed @{owner}'s totem!", battle=True)
                    await self._send_battle_message(f"Monster #{monster_index} {monster.get('name')} destroyed @{owner}'s totem!")
                    # Remove from alive_targets
                    alive_targets = [t for t in alive_targets if not (t["type"] == "totem" and t["data"]["id"] == totem_data["id"])]
            
            elif target["type"] == "imp":
                # Attack imp
                imp_data = target["data"]
                if imp_data.get("totem_shield_available"):
                    imp_data["totem_shield_available"] = False
                    owner = imp_data.get("owner", "?")
                    self._log_event(f"Shield Totem: prevented damage to @{owner}'s imp.", battle=True)
                    await self._send_battle_message(f"ðŸ›¡ï¸ Shield Totem blocks the hit on @{owner}'s imp!")
                    continue
                imp_data["alive"] = False
                owner = imp_data.get("owner", "?")
                self._log_event(f"Monster: {monster.get('name')} destroyed @{owner}'s imp!", battle=True)
                await self._send_battle_message(f"Monster #{monster_index} {monster.get('name')} destroyed @{owner}'s imp!")
                # Remove from alive_targets
                alive_targets = [t for t in alive_targets if not (t["type"] == "imp" and t["data"]["id"] == imp_data["id"])]
    
            elif target["type"] == "green_arrow":
                # Attack green arrow
                arrow_data = target["data"]
                if arrow_data.get("totem_shield_available"):
                    arrow_data["totem_shield_available"] = False
                    owner = arrow_data.get("owner", "?")
                    self._log_event(f"Shield Totem: prevented damage to @{owner}'s Green Arrow.", battle=True)
                    await self._send_battle_message(f"ðŸ›¡ï¸ Shield Totem blocks the hit on @{owner}'s Green Arrow!")
                    continue
                arrow_data["alive"] = False
                owner = arrow_data.get("owner", "?")
                self._log_event(
                    f"Monster: {monster.get('name')} destroyed @{owner}'s Green Arrow!",
                    battle=True,
                )
                await self._send_battle_message(
                    f"Monster #{monster_index} {monster.get('name')} destroyed @{owner}'s Green Arrow!"
                )
                # Remove from alive_targets
                alive_targets = [
                    t for t in alive_targets
                    if not (t["type"] == "green_arrow" and t["data"]["id"] == arrow_data["id"])
                ]
    
            elif target["type"] == "dragon":
                # Attack dragon
                dragon_data = target["data"]
                if dragon_data.get("totem_shield_available"):
                    dragon_data["totem_shield_available"] = False
                    owner = dragon_data.get("owner", "?")
                    self._log_event(f"Shield Totem: prevented damage to @{owner}'s dragon.", battle=True)
                    await self._send_battle_message(f"ðŸ›¡ï¸ Shield Totem blocks the hit on @{owner}'s dragon!")
                    continue
                dragon_hp = int(dragon_data.get("hp", 0))
                dragon_data["hp"] = max(0, dragon_hp - damage)
                if dragon_data["hp"] > 0:
                    owner = dragon_data.get("owner", "?")
                    self._log_event(
                        f"Monster: {monster.get('name')} hit @{owner}'s dragon for {damage}.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"Monster #{monster_index} {monster.get('name')} hit @{owner}'s dragon for {damage}."
                    )
                    continue
                dragon_data["alive"] = False
                owner = dragon_data.get("owner", "?")
                self._log_event(f"Monster: {monster.get('name')} destroyed @{owner}'s dragon!", battle=True)
                await self._send_battle_message(f"Monster #{monster_index} {monster.get('name')} destroyed @{owner}'s dragon!")
                # Remove from alive_targets
                alive_targets = [t for t in alive_targets if not (t["type"] == "dragon" and t["data"]["id"] == dragon_data["id"])]
    
            elif target["type"] == "undead":
                pet_data = target["data"]
                owner = pet_data.get("owner", "?")
                pet_type = str(pet_data.get("pet_type", "undead")).lower()
                pet_name = pet_type.capitalize()
                if pet_data.get("totem_shield_available"):
                    pet_data["totem_shield_available"] = False
                    self._log_event(f"Shield Totem: prevented damage to @{owner}'s {pet_name}.", battle=True)
                    await self._send_battle_message(f"ðŸ›¡ï¸ Shield Totem blocks the hit on @{owner}'s {pet_name}!")
                    continue
                mitigation = int(pet_data.get("mitigation", 0)) if pet_type == "blob" else 0
                pet_damage = max(1, damage - mitigation)
    
                hp_before = int(pet_data.get("hp", 0))
                pet_data["hp"] = max(0, hp_before - pet_damage)
                if pet_data["hp"] > 0:
                    self._log_event(
                        f"Monster: {monster.get('name')} hit @{owner}'s {pet_name} for {pet_damage}.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"Monster #{monster_index} {monster.get('name')} hit @{owner}'s {pet_name} for {pet_damage}."
                    )
                    continue
    
                pet_data["alive"] = False
                self._log_event(
                    f"Monster: {monster.get('name')} destroyed @{owner}'s {pet_name}!",
                    battle=True,
                )
                await self._send_battle_message(
                    f"Monster #{monster_index} {monster.get('name')} destroyed @{owner}'s {pet_name}!"
                )
                alive_targets = [
                    t for t in alive_targets
                    if not (t.get("type") == "undead" and t.get("data", {}).get("id") == pet_data.get("id"))
                ]
    
            elif target["type"] == "streamer_pet":
                pet_data = target["data"]
                owner = pet_data.get("owner", "?")
                pet_type = str(pet_data.get("pet_type", "streamer_pet")).lower()
                pet_name = "Timberwolf" if pet_type == "timberwolf" else "Gordie Howe"
                if pet_data.get("totem_shield_available"):
                    pet_data["totem_shield_available"] = False
                    self._log_event(f"Shield Totem: prevented damage to @{owner}'s {pet_name}.", battle=True)
                    await self._send_battle_message(f"ðŸ›¡ï¸ Shield Totem blocks the hit on @{owner}'s {pet_name}!")
                    continue
                hp_before = int(pet_data.get("hp", 0))
                pet_data["hp"] = max(0, hp_before - damage)
                if pet_data["hp"] > 0:
                    self._log_event(
                        f"Monster: {monster.get('name')} hit @{owner}'s {pet_name} for {damage}.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"Monster #{monster_index} {monster.get('name')} hit @{owner}'s {pet_name} for {damage}."
                    )
                    continue
    
                pet_data["alive"] = False
                self._log_event(
                    f"Monster: {monster.get('name')} destroyed @{owner}'s {pet_name}!",
                    battle=True,
                )
                await self._send_battle_message(
                    f"Monster #{monster_index} {monster.get('name')} destroyed @{owner}'s {pet_name}!"
                )
                alive_targets = [
                    t for t in alive_targets
                    if not (t.get("type") == "streamer_pet" and t.get("data", {}).get("id") == pet_data.get("id"))
                ]
    
            elif target["type"] == "buff_pet":
                pet_data = target["data"]
                owner = pet_data.get("owner", "?")
                pet_type = str(pet_data.get("pet_type", "buff_pet")).lower()
                pet_name = "Kid" if pet_type == "kid" else "Franklin"
                self._log_event(
                    f"Monster: {monster.get('name')} tried to hit @{owner}'s {pet_name}, but it is invulnerable.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"ðŸ›¡ï¸ Monster #{monster_index} {monster.get('name')} tried to hit @{owner}'s {pet_name}, but it is invulnerable!"
                )
                continue
    
            elif target["type"] == "spirit_well":
                well_data = target["data"]
                owner = well_data.get("owner", "?")
                if well_data.get("totem_shield_available"):
                    well_data["totem_shield_available"] = False
                    self._log_event(f"Shield Totem: prevented damage to @{owner}'s Spirit Well.", battle=True)
                    await self._send_battle_message(f"ðŸ›¡ï¸ Shield Totem blocks the hit on @{owner}'s Spirit Well!")
                    continue
                hp_before = int(well_data.get("hp", 0))
                well_data["hp"] = max(0, hp_before - damage)
                if well_data["hp"] > 0:
                    self._log_event(
                        f"Monster: {monster.get('name')} hit @{owner}'s Spirit Well for {damage}.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"Monster #{monster_index} {monster.get('name')} hit @{owner}'s Spirit Well for {damage}."
                    )
                    continue
                well_data["alive"] = False
                self._log_event(
                    f"Monster: {monster.get('name')} destroyed @{owner}'s Spirit Well!",
                    battle=True,
                )
                await self._send_battle_message(
                    f"Monster #{monster_index} {monster.get('name')} destroyed @{owner}'s Spirit Well!"
                )
                alive_targets = [
                    t for t in alive_targets
                    if not (t.get("type") == "spirit_well" and t.get("data", {}).get("id") == well_data.get("id"))
                ]
            
            else:
                # Attack player
                target_name = target["name"]
                target_user = self.state.get_user(target_name)
    
                owner_kids = [
                    p for p in session.get("buff_pets", [])
                    if p.get("alive")
                    and str(p.get("owner", "")).lower() == target_name
                    and str(p.get("pet_type", "")).lower() == "kid"
                ]
                if owner_kids:
                    kid_pet = owner_kids[0]
                    intercept_chance = float(kid_pet.get("intercept_chance", BUFF_KID_INTERCEPT_CHANCE))
                    if random.random() < intercept_chance:
                        target_user["buff_kid_intercept_triggered"] = True
                        alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
                        intercept_target = random.choice(alive_monsters) if alive_monsters else None
    
                        if intercept_target:
                            hp_before = int(intercept_target.get("hp", 0))
                            dealt = max(0, hp_before)
                            intercept_target["hp"] = 0
                            if intercept_target.get("alive"):
                                intercept_target["alive"] = False
                                intercept_target["killed_by"] = target_name
                                self._add_pet_owner_damage(target_name, dealt)
                                target_user["monsters_killed"] = int(target_user.get("monsters_killed", 0)) + 1
                                target_user["killing_blows"] = int(target_user.get("killing_blows", 0)) + 1
                                if intercept_target.get("is_loot_goblin"):
                                    await self._award_loot_goblin_rewards(
                                        session,
                                        target_name,
                                        int(intercept_target.get("level", 1)),
                                    )
    
                        self._log_event(
                            f"KID INTERCEPT: @{target_name}'s Kid intercepted {monster.get('name')} ({int(intercept_chance * 100)}% proc) and shot down {intercept_target.get('name') if intercept_target else 'a target'}.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"âœˆï¸ KID INTERCEPT! @{target_name}'s Kid splashes {intercept_target.get('name') if intercept_target else 'a mob'} out of the sky."
                        )
                        continue
    
                if target_user.get("totem_shield_available"):
                    target_user["totem_shield_available"] = False
                    self._log_event(f"Shield Totem: prevented damage to @{target_name}.", battle=True)
                    await self._send_battle_message(f"ðŸ›¡ï¸ Shield Totem blocks the hit on @{target_name}!")
                    continue
                
                # Check for Meatwad evasion forms
                form_data = self._get_effective_meatwad_form(target_user, session)
                if form_data and form_data.get("effect_type") == "evasion":
                    evasion_chance = float(form_data.get("effect_value", 0))
                    if random.random() < evasion_chance:
                        form_name = form_data.get("name", "Unknown")
                        await self._send_battle_message(
                            f"âœ¨ {form_name}: @{target_name} evades the attack!"
                        )
                        self._log_event(f"Meatwad evasion: @{target_name} as {form_name} evaded attack.", battle=True)
                        continue
                
                # Apply damage mitigation for Warriors (scales with level)
                target_class = target_user.get("class_name", "Derp Clone")
                if target_class == "Warrior":
                    total_xp = int(target_user.get("xp", 0))
                    warrior_level = self._get_level_from_xp(total_xp, target_user)
                    # Base mitigation (2) + level scaling (0.75 per level starting at level 2)
                    mitigation = WARRIOR_DAMAGE_MITIGATION + (warrior_level - 1) * DAMAGE_MITIGATION_PER_LEVEL
                    damage = max(1, damage - mitigation)
                
                # Apply Meatwad transformation defense bonuses
                if form_data:
                    effect_type = form_data.get("effect_type", "")
                    effect_value = form_data.get("effect_value", 0)
                    
                    if effect_type == "defense":
                        # Direct defense (Igloo, Humanoid 2, Bricks, Wall)
                        damage = max(1, damage - int(effect_value))
                    elif effect_type == "party_defense":
                        # Party-wide defense (Bridge)
                        damage = max(1, damage - int(effect_value))
                    elif effect_type == "balanced":
                        # Balanced form (Humanoid 3) - defense + damage
                        damage = max(1, damage - int(effect_value))
                    elif effect_type == "five_boost":
                        # Number 5 form - 5% reduction
                        damage = max(1, int(damage * (1 - effect_value)))
                
                hp_before = int(target_user.get("hp_current", DEFAULT_PLAYER_HP))
                target_user["hp_current"] = max(0, hp_before - damage)
                
                # Apply Meatwad reflect damage
                if form_data:
                    effect_type = form_data.get("effect_type", "")
                    if effect_type == "reflect":
                        reflect_damage = int(form_data.get("effect_value", 0))
                        monster["hp"] = max(0, monster.get("hp", 0) - reflect_damage)
                        form_name = form_data.get("name", "Unknown")
                        await self._send_battle_message(f"ðŸŒ¶ï¸ {form_name}: @{target_name} reflects {reflect_damage} damage!")
                        self._log_event(f"Meatwad reflect: @{target_name} as {form_name} reflected {reflect_damage} damage.", battle=True)
                        
                        if monster.get("hp", 0) <= 0 and monster.get("alive"):
                            monster["alive"] = False
                            monster["killed_by"] = target_name
                            target_user["monsters_killed"] = int(target_user.get("monsters_killed", 0)) + 1
                            target_user["killing_blows"] = int(target_user.get("killing_blows", 0)) + 1
                            await self._send_battle_message(f"ðŸ’¥ {form_name}: Reflect damage kills {monster.get('name')}!")
                    
                    elif effect_type == "counter":
                        # Counter attack (Middle Finger)
                        counter_damage = int(form_data.get("effect_value", 0))
                        counter_hp_before = int(monster.get("hp", 0))
                        counter_dealt = min(counter_damage, counter_hp_before)
                        monster["hp"] = max(0, counter_hp_before - counter_damage)
                        form_name = form_data.get("name", "Unknown")
                        await self._send_battle_message(f"ðŸ–• {form_name}: @{target_name} counters for {counter_damage} damage!")
                        self._log_event(f"Meatwad counter: @{target_name} as {form_name} countered for {counter_damage} damage.", battle=True)
                        target_user["lifetime_monster_damage"] = int(target_user.get("lifetime_monster_damage", 0)) + counter_dealt
                        target_user["damage_done"] = int(target_user.get("damage_done", 0)) + counter_dealt
                        
                        if monster.get("hp", 0) <= 0 and monster.get("alive"):
                            monster["alive"] = False
                            monster["killed_by"] = target_name
                            target_user["monsters_killed"] = int(target_user.get("monsters_killed", 0)) + 1
                            target_user["killing_blows"] = int(target_user.get("killing_blows", 0)) + 1
                            await self._send_battle_message(f"ðŸ’¥ {form_name}: Counter attack kills {monster.get('name')}!")
                
                if hp_before > 0 and target_user["hp_current"] == 0:
                    if not await self._trigger_archangel_death_passive(session, target_name):
                        target_user["times_knocked_out"] = int(target_user.get("times_knocked_out", 0)) + 1
                        despawned = self._despawn_buff_pets_for_owner(session, target_name)
                        if despawned:
                            await self._send_battle_message(
                                f"ðŸ’¨ {', '.join(despawned)} vanish as @{target_name} is knocked out!"
                            )
                    # Remove from alive_targets
                    alive_targets = [t for t in alive_targets if not (t["type"] == "player" and t["name"] == target_name)]
                
                await self._send_battle_message(
                    f"Monster #{monster_index} {monster.get('name')} attacks @{target_name} for {damage}."
                )
                self._log_event(
                    f"Monster: {monster.get('name')} attacks @{target_name} for {damage}.",
                    battle=True,
                )
        
        # Now let imps attack
        imps = [imp for imp in session.get("imps", []) if imp.get("alive")]
        if imps:
            alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
            for imp in imps:
                if not alive_monsters:
                    break
                imp_damage = imp.get("damage", 1)
                target_monster = random.choice(alive_monsters)
                hp_before = int(target_monster.get("hp", 0))
                dealt = min(int(imp_damage), hp_before)
                target_monster["hp"] = max(0, hp_before - int(imp_damage))
                owner = imp.get("owner", "?")
                self._add_pet_owner_damage(owner, dealt)
                self._log_event(f"Imp: @{owner}'s imp fireballs {target_monster.get('name')} for {dealt} damage.", battle=True)
                await self._send_battle_message(f"@{owner}'s imp fireballs {target_monster.get('name')} for {dealt} damage!")
                
                if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                    target_monster["alive"] = False
                    alive_monsters.remove(target_monster)
                    self._log_event(f"Monster down: {target_monster.get('name')} defeated by @{owner}'s imp.", battle=True)
                    
                    # Check if loot goblin was killed by imp - special rewards
                    if target_monster.get("is_loot_goblin"):
                        await self._award_loot_goblin_rewards(
                            session,
                            owner,
                            int(target_monster.get("level", 1)),
                            by_imp=True,
                        )
    
        dragons = [dragon for dragon in session.get("dragons", []) if dragon.get("alive")]
        if dragons:
            alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
            for dragon in dragons:
                if not alive_monsters:
                    break
                owner = dragon.get("owner", "?")
                bite_damage, dragon_damage, claw_damage = self._get_dragon_combat_stats(owner)
                dragon["attack_damage"] = bite_damage
                dragon["damage"] = dragon_damage
                dragon["claw_damage"] = claw_damage
                bite_target = random.choice(alive_monsters)
                bite_hp_before = int(bite_target.get("hp", 0))
                bite_dealt = min(bite_damage, bite_hp_before)
                bite_target["hp"] = max(0, bite_hp_before - bite_damage)
                self._add_pet_owner_damage(owner, bite_dealt)
                self._log_event(
                    f"Dragon: @{owner}'s dragon bites {bite_target.get('name')} for {bite_dealt} damage.",
                    battle=True,
                )
                await self._send_battle_message(
                    f"@{owner}'s dragon bites {bite_target.get('name')} for {bite_dealt} damage!"
                )
                if bite_target.get("hp", 0) <= 0 and bite_target.get("alive"):
                    bite_target["alive"] = False
                    if bite_target in alive_monsters:
                        alive_monsters.remove(bite_target)
                    self._log_event(
                        f"Monster down: {bite_target.get('name')} defeated by @{owner}'s dragon.",
                        battle=True,
                    )
                    if bite_target.get("is_loot_goblin"):
                        await self._award_loot_goblin_rewards(
                            session,
                            owner,
                            int(bite_target.get("level", 1)),
                        )
    
                if alive_monsters and random.random() < float(dragon.get("claw_chance", DRAGON_CLAW_CHANCE)):
                    claw_target = random.choice(alive_monsters)
                    claw_hp_before = int(claw_target.get("hp", 0))
                    claw_dealt = min(claw_damage, claw_hp_before)
                    claw_target["hp"] = max(0, claw_hp_before - claw_damage)
                    claw_target["bleed_stacks"] = int(claw_target.get("bleed_stacks", 0)) + 1
                    claw_target["bleed_rounds_remaining"] = max(
                        int(claw_target.get("bleed_rounds_remaining", 0)),
                        DRAGON_CLAW_BLEED_DURATION,
                    )
                    self._add_pet_owner_damage(owner, claw_dealt)
                    self._log_event(
                        f"Dragon CLAW: @{owner}'s dragon mauls {claw_target.get('name')} for {claw_dealt} and applies bleed.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"ðŸ‰ @{owner}'s dragon uses CLAW on {claw_target.get('name')} for {claw_dealt}! Bleed applied."
                    )
                    if claw_target.get("hp", 0) <= 0 and claw_target.get("alive"):
                        claw_target["alive"] = False
                        if claw_target in alive_monsters:
                            alive_monsters.remove(claw_target)
                        self._log_event(
                            f"Monster down: {claw_target.get('name')} defeated by @{owner}'s dragon CLAW.",
                            battle=True,
                        )
                        if claw_target.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(
                                session,
                                owner,
                                int(claw_target.get("level", 1)),
                            )
    
                hits = 0
                for monster in alive_monsters:
                    if random.random() < DRAGON_DOT_CHANCE:
                        current_damage = int(monster.get("dragon_dot_damage", 0))
                        monster["dragon_dot_damage"] = current_damage + dragon_damage
                        monster["dragon_dot_rounds_remaining"] = DRAGON_DOT_DURATION
                        monster["dragon_dot_owner"] = owner
                        hits += 1
                if hits > 0:
                    self._log_event(
                        f"Dragonfire: @{owner}'s dragon scorched {hits} enemies (stacking DoT).",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"@{owner}'s dragon scorched {hits} enemies with dragonfire!"
                    )
    
        streamer_pets = [pet for pet in session.get("streamer_pets", []) if pet.get("alive")]
        if streamer_pets:
            alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
            for pet in streamer_pets:
                if not alive_monsters:
                    break
                owner = pet.get("owner", "?")
                pet_type = str(pet.get("pet_type", "")).lower()
    
                if pet_type == "timberwolf":
                    if random.random() < 0.5:
                        target_monster = random.choice(alive_monsters)
                        ppc_damage = int(pet.get("ppc_damage", STREAMER_PET_TIMBERWOLF_PPC_DAMAGE))
                        hp_before = int(target_monster.get("hp", 0))
                        dealt = min(ppc_damage, hp_before)
                        target_monster["hp"] = max(0, hp_before - ppc_damage)
                        self._add_pet_owner_damage(owner, dealt)
                        self._log_event(
                            f"Timberwolf: @{owner}'s Timberwolf fires PPC at {target_monster.get('name')} for {dealt}.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"@{owner}'s Timberwolf fires PPC at {target_monster.get('name')} for {dealt}!"
                        )
    
                        stun_chance = float(pet.get("ppc_stun_chance", STREAMER_PET_TIMBERWOLF_PPC_STUN_CHANCE))
                        if target_monster.get("alive") and random.random() < stun_chance:
                            target_monster["stun_turns_remaining"] = max(
                                1,
                                int(target_monster.get("stun_turns_remaining", 0)),
                            )
                            await self._send_battle_message(
                                f"PPC impact! {target_monster.get('name')} is stunned."
                            )
    
                        if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                            target_monster["alive"] = False
                            alive_monsters.remove(target_monster)
                            self._log_event(
                                f"Monster down: {target_monster.get('name')} defeated by @{owner}'s Timberwolf.",
                                battle=True,
                            )
                            if target_monster.get("is_loot_goblin"):
                                await self._award_loot_goblin_rewards(
                                    session,
                                    owner,
                                    int(target_monster.get("level", 1)),
                                )
                    else:
                        lrm_percent = float(pet.get("lrm_percent", STREAMER_PET_TIMBERWOLF_LRM_PERCENT))
                        total_dealt = 0
                        for target_monster in list(alive_monsters):
                            if not target_monster.get("alive"):
                                continue
                            lrm_damage = max(1, int(int(target_monster.get("max_hp", 1)) * lrm_percent))
                            hp_before = int(target_monster.get("hp", 0))
                            dealt = min(lrm_damage, hp_before)
                            target_monster["hp"] = max(0, hp_before - lrm_damage)
                            total_dealt += dealt
                            self._add_pet_owner_damage(owner, dealt)
                            if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                                target_monster["alive"] = False
                                alive_monsters.remove(target_monster)
                                self._log_event(
                                    f"Monster down: {target_monster.get('name')} defeated by @{owner}'s Timberwolf LRM.",
                                    battle=True,
                                )
                                if target_monster.get("is_loot_goblin"):
                                    await self._award_loot_goblin_rewards(
                                        session,
                                        owner,
                                        int(target_monster.get("level", 1)),
                                    )
                        self._log_event(
                            f"Timberwolf: @{owner}'s Timberwolf fires LRM for {total_dealt} total damage.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"@{owner}'s Timberwolf fires LRM barrage for {total_dealt} total damage!"
                        )
                    continue
    
                if pet_type == "gordie_howe":
                    gordie_action = random.choice(["goal", "assist", "fight"])
                    if gordie_action == "goal":
                        target_monster = random.choice(alive_monsters)
                        goal_base = int(pet.get("goal_damage", STREAMER_PET_GORDIE_GOAL_DAMAGE))
                        goal_damage = int(goal_base * CRIT_MULTIPLIER)
                        hp_before = int(target_monster.get("hp", 0))
                        dealt = min(goal_damage, hp_before)
                        target_monster["hp"] = max(0, hp_before - goal_damage)
                        self._add_pet_owner_damage(owner, dealt)
                        self._log_event(
                            f"Gordie Howe: @{owner}'s Gordie scores GOAL on {target_monster.get('name')} for {dealt} (CRIT).",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"ðŸ¥… @{owner}'s Gordie Howe scores GOAL on {target_monster.get('name')} for {dealt} (CRIT)!"
                        )
                        if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                            target_monster["alive"] = False
                            alive_monsters.remove(target_monster)
                            self._log_event(
                                f"Monster down: {target_monster.get('name')} defeated by @{owner}'s Gordie Howe.",
                                battle=True,
                            )
                            if target_monster.get("is_loot_goblin"):
                                await self._award_loot_goblin_rewards(
                                    session,
                                    owner,
                                    int(target_monster.get("level", 1)),
                                )
                        continue
    
                    if gordie_action == "assist":
                        ally_candidates = [
                            name for name in session.get("participants", [])
                            if int(self.state.get_user(name).get("hp_current", 0)) > 0
                        ]
                        if ally_candidates:
                            ally_name = random.choice(ally_candidates)
                            ally_data = self.state.get_user(ally_name)
                            ally_data["next_attack_forced_crit"] = int(ally_data.get("next_attack_forced_crit", 0)) + 1
                            self._log_event(
                                f"Gordie Howe: @{owner}'s Gordie gives ASSIST to @{ally_name} (next attack crit).",
                                battle=True,
                            )
                            await self._send_battle_message(
                                f"ðŸ’ @{owner}'s Gordie Howe assists @{ally_name}! Their next attack/skill will crit."
                            )
                        continue
    
                    fight_percent = float(pet.get("fight_percent", STREAMER_PET_GORDIE_FIGHT_PERCENT))
                    targets = random.sample(alive_monsters, k=min(STREAMER_PET_GORDIE_FIGHT_TARGETS, len(alive_monsters)))
                    total_dealt = 0
                    for target_monster in targets:
                        fight_damage = max(1, int(int(target_monster.get("max_hp", 1)) * fight_percent))
                        hp_before = int(target_monster.get("hp", 0))
                        dealt = min(fight_damage, hp_before)
                        target_monster["hp"] = max(0, hp_before - fight_damage)
                        total_dealt += dealt
                        self._add_pet_owner_damage(owner, dealt)
                        if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                            target_monster["alive"] = False
                            if target_monster in alive_monsters:
                                alive_monsters.remove(target_monster)
                            self._log_event(
                                f"Monster down: {target_monster.get('name')} dropped in Gordie fight.",
                                battle=True,
                            )
                            if target_monster.get("is_loot_goblin"):
                                await self._award_loot_goblin_rewards(
                                    session,
                                    owner,
                                    int(target_monster.get("level", 1)),
                                )
                    self._log_event(
                        f"Gordie Howe: @{owner}'s Gordie starts a FIGHT for {total_dealt} total damage.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"ðŸ¥Š @{owner}'s Gordie Howe starts a FIGHT and deals {total_dealt} total damage!"
                    )
    
        buff_pets = [pet for pet in session.get("buff_pets", []) if pet.get("alive")]
        if buff_pets:
            alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
            for pet in buff_pets:
                if not alive_monsters:
                    break
                owner = str(pet.get("owner", "")).lower()
                pet_type = str(pet.get("pet_type", "")).lower()
    
                if pet_type == "kid":
                    continue
    
                if pet_type == "franklin":
                    target_monster = random.choice(alive_monsters)
                    franklin_damage = max(1, int(pet.get("damage", BUFF_FRANKLIN_BASE_DAMAGE)))
                    did_crit = random.random() < float(pet.get("crit_chance", BUFF_FRANKLIN_CRIT_CHANCE))
                    if did_crit:
                        franklin_damage = int(franklin_damage * CRIT_MULTIPLIER)
    
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(franklin_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - franklin_damage)
                    self._add_pet_owner_damage(owner, dealt)
    
                    if did_crit:
                        owner_data = self.state.get_user(owner)
                        owner_data["buff_franklin_crit_triggered"] = True
                        owner_data["buff_franklin_jdam_buff_triggered"] = True
                        owner_data["buff_jdam_forced_crit_charges"] = int(owner_data.get("buff_jdam_forced_crit_charges", 0)) + BUFF_FRANKLIN_JDAM_CRIT_CHARGES
                        intercept_bonus_pct = int(BUFF_FRANKLIN_INTERCEPT_CHANCE_BONUS * 100)
                        jdam_bonus_pct = int(BUFF_FRANKLIN_JDAM_CRIT_CHANCE_BONUS * 100)
                        self._log_event(
                            f"Franklin buff: @{owner} gained +{jdam_bonus_pct}% JDAM crit chance and +{intercept_bonus_pct}% Kid intercept chance.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"âœ¨ @{owner}'s Franklin CRITS {target_monster.get('name')}! +{jdam_bonus_pct}% JDAM crit chance and +{intercept_bonus_pct}% Kid intercept chance."
                        )
    
                    self._log_event(
                        f"Franklin: @{owner}'s Franklin hit {target_monster.get('name')} for {dealt}{' (CRIT)' if did_crit else ''}.",
                        battle=True,
                    )
    
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        alive_monsters.remove(target_monster)
                        self._log_event(
                            f"Monster down: {target_monster.get('name')} defeated by @{owner}'s Franklin.",
                            battle=True,
                        )
                        if target_monster.get("is_loot_goblin"):
                            await self._award_loot_goblin_rewards(
                                session,
                                owner,
                                int(target_monster.get("level", 1)),
                            )
    
        undead_pets = [pet for pet in session.get("undead_pets", []) if pet.get("alive")]
        if undead_pets:
            alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
            for pet in undead_pets:
                if not alive_monsters:
                    break
                owner = pet.get("owner", "?")
                pet_type = str(pet.get("pet_type", "")).lower()
    
                if pet_type == "blob":
                    target_monster = random.choice(alive_monsters)
                    blob_damage = int(pet.get("damage", REVENANT_BLOB_DAMAGE))
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(blob_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - blob_damage)
                    self._add_pet_owner_damage(owner, dealt)
                    self._log_event(
                        f"Blob: @{owner}'s Blob slams {target_monster.get('name')} for {dealt} damage.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"@{owner}'s Blob slams {target_monster.get('name')} for {dealt} damage!"
                    )
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        alive_monsters.remove(target_monster)
                        self._log_event(f"Monster down: {target_monster.get('name')} defeated by @{owner}'s Blob.", battle=True)
                    continue
    
                if pet_type == "ghoul":
                    target_monster = random.choice(alive_monsters)
                    owner_data = self.state.get_user(owner)
                    revenant_level = self._get_level_from_xp(int(owner_data.get("xp", 0)), owner_data)
                    base_ghoul_damage = int(pet.get("damage", REVENANT_GHOUL_DAMAGE))
                    ghoul_damage = base_ghoul_damage + max(0, revenant_level - 1) * REVENANT_GHOUL_DAMAGE_PER_LEVEL
                    totem_bonus = int(self._get_totem_buff(session).get("damage_bonus", 0))
                    ghoul_damage += totem_bonus
                    if random.random() < float(pet.get("crit_chance", REVENANT_GHOUL_CRIT_CHANCE)):
                        ghoul_damage = int(ghoul_damage * CRIT_MULTIPLIER)
                    hp_before = int(target_monster.get("hp", 0))
                    dealt = min(ghoul_damage, hp_before)
                    target_monster["hp"] = max(0, hp_before - ghoul_damage)
                    self._add_pet_owner_damage(owner, dealt)
    
                    current_poison = int(target_monster.get("ghoul_poison_damage", 0))
                    next_poison = 1 if current_poison <= 0 else current_poison + current_poison
                    target_monster["ghoul_poison_damage"] = next_poison
                    target_monster["ghoul_poison_rounds_remaining"] = REVENANT_GHOUL_POISON_DURATION
                    target_monster["ghoul_poison_owner"] = owner
    
                    self._log_event(
                        f"Ghoul: @{owner}'s Ghoul hit {target_monster.get('name')} for {dealt}; poison now {next_poison} for 3 turns.",
                        battle=True,
                    )
                    await self._send_battle_message(
                        f"@{owner}'s Ghoul claws {target_monster.get('name')} for {dealt}! Poison stacks to {next_poison} (3 turns)."
                    )
                    if target_monster.get("hp", 0) <= 0 and target_monster.get("alive"):
                        target_monster["alive"] = False
                        alive_monsters.remove(target_monster)
                        self._log_event(f"Monster down: {target_monster.get('name')} defeated by @{owner}'s Ghoul.", battle=True)
                    continue
    
                if pet_type == "wisp":
                    rez_cooldown = int(pet.get("rez_cooldown", 0))
                    if rez_cooldown > 0:
                        pet["rez_cooldown"] = rez_cooldown - 1
    
                    participants = session.get("participants", [])
                    knocked_out = [
                        name for name in participants
                        if int(self.state.get_user(name).get("hp_current", 0)) <= 0
                    ]
                    if knocked_out and int(pet.get("rez_cooldown", 0)) <= 0:
                        rez_target = knocked_out[0]
                        target_data = self.state.get_user(rez_target)
                        max_hp = int(target_data.get("hp_max", DEFAULT_PLAYER_HP))
                        rez_hp = max(1, max_hp // 2)
                        target_data["hp_current"] = rez_hp
                        pet["rez_cooldown"] = REVENANT_WISP_REZ_COOLDOWN_TURNS
                        self._log_event(
                            f"Wisp: @{owner}'s Wisp resurrected @{rez_target} with {rez_hp} HP.",
                            battle=True,
                        )
                        await self._send_battle_message(
                            f"@{owner}'s Wisp resurrected @{rez_target} with {rez_hp} HP!"
                        )
    
                    heal_target = None
                    heal_value = 0
                    lowest_missing = 0
                    for name in participants:
                        data = self.state.get_user(name)
                        hp_now = int(data.get("hp_current", 0))
                        hp_max = int(data.get("hp_max", DEFAULT_PLAYER_HP))
                        if hp_now <= 0:
                            continue
                        missing = hp_max - hp_now
                        if missing > lowest_missing:
                            lowest_missing = missing
                            heal_target = name
                    if heal_target:
                        target_data = self.state.get_user(heal_target)
                        hp_now = int(target_data.get("hp_current", 0))
                        hp_max = int(target_data.get("hp_max", DEFAULT_PLAYER_HP))
                        owner_data = self.state.get_user(owner)
                        owner_level = self._get_level_from_xp(int(owner_data.get("xp", 0)), owner_data)
                        wisp_heal_value = REVENANT_WISP_HEAL + max(0, owner_level - 1) * REVENANT_WISP_HEAL_PER_LEVEL
                        heal_value = min(wisp_heal_value, hp_max - hp_now)
                        if heal_value > 0:
                            target_data["hp_current"] = hp_now + heal_value
                            owner_data = self.state.get_user(owner)
                            owner_data["healing_done"] = int(owner_data.get("healing_done", 0)) + heal_value
                            pet["energy"] = int(pet.get("energy", 0)) + 1
                            self._log_event(
                                f"Wisp: @{owner}'s Wisp healed @{heal_target} for {heal_value}.",
                                battle=True,
                            )
                            await self._send_battle_message(
                                f"@{owner}'s Wisp healed @{heal_target} for {heal_value}."
                            )
    
                    if int(pet.get("energy", 0)) >= 3:
                        healed_players = 0
                        total_heal = 0
                        for name in participants:
                            data = self.state.get_user(name)
                            hp_now = int(data.get("hp_current", 0))
                            hp_max = int(data.get("hp_max", DEFAULT_PLAYER_HP))
                            if hp_now <= 0:
                                continue
                            owner_data = self.state.get_user(owner)
                            owner_level = self._get_level_from_xp(int(owner_data.get("xp", 0)), owner_data)
                            party_wisp_heal_value = REVENANT_WISP_PARTY_HEAL + max(0, (owner_level - 1) // REVENANT_WISP_PARTY_HEAL_LEVEL_STEP)
                            healed = min(party_wisp_heal_value, hp_max - hp_now)
                            if healed <= 0:
                                continue
                            data["hp_current"] = hp_now + healed
                            healed_players += 1
                            total_heal += healed
                        pet["energy"] = 0
                        if healed_players > 0:
                            owner_data = self.state.get_user(owner)
                            owner_data["healing_done"] = int(owner_data.get("healing_done", 0)) + total_heal
                            self._log_event(
                                f"Wisp: @{owner}'s Wisp released party heal for {total_heal} total HP.",
                                battle=True,
                            )
                            await self._send_battle_message(
                                f"@{owner}'s Wisp released soothing energy: {total_heal} total party healing!"
                            )
        
        self.state.save_state()
    
    async def _check_party_defeat(self) -> bool:
        session = self.state.session()
        participants = session.get("participants", [])
        if not participants:
            return False
        if any(w.get("alive") for w in session.get("spirit_wells", [])):
            return False
        for username in participants:
            user = self.state.get_user(username)
            if int(user.get("hp_current", DEFAULT_PLAYER_HP)) > 0:
                return False
        for username in participants:
            user = self.state.get_user(username)
            user["summoner_dot_damage"] = 0
            user["summoner_dot_rounds_remaining"] = 0
            user["buff_takeoff_used"] = False
            user["buff_kid_intercept_triggered"] = False
            user["buff_franklin_crit_triggered"] = False
            user["buff_franklin_jdam_buff_triggered"] = False
            user["buff_jdam_crit_triggered"] = False
            user["buff_jdam_forced_crit_charges"] = 0
        self._reset_deputy_battle_cooldowns(participants)
        self._clear_alchemist_brew_bonuses(participants)
        session["battle_active"] = False
        session["battle_id"] = None
        session["monsters"] = []
        session["phase"] = "idle"
        session["action_window_end"] = None
        session["join_window_end"] = None
        session["participants"] = []
        session["action_queue"] = []
        session["totems"] = []
        session["imps"] = []
        session["dragons"] = []
        session["green_arrows"] = []
        session["undead_pets"] = []
        session["streamer_pets"] = []
        session["buff_pets"] = []
        session["spirit_wells"] = []
        session["barbarian_shout_rounds_remaining"] = 0
        session["battle_stat_baseline"] = {}
        self._log_event("Battle ended: party defeated.", battle=True)
        await self._send_battle_message("The party has fallen. Battle lost.")
        self.state.save_state()
        self._broadcast_state()
        return True
    
    async def _check_battle_end(self):
        session = self.state.session()
        if any(monster.get("alive") for monster in session.get("monsters", [])):
            return
        participants = session.get("participants", [])
        if not participants:
            logging.warning("Battle end check triggered but no participants found")
            return
        for username in participants:
            user = self.state.get_user(username)
            user["summoner_dot_damage"] = 0
            user["summoner_dot_rounds_remaining"] = 0
            user["buff_takeoff_used"] = False
            user["buff_kid_intercept_triggered"] = False
            user["buff_franklin_crit_triggered"] = False
            user["buff_franklin_jdam_buff_triggered"] = False
            user["buff_jdam_crit_triggered"] = False
            user["buff_jdam_forced_crit_charges"] = 0
        self._reset_deputy_battle_cooldowns(participants)
        self._clear_alchemist_brew_bonuses(participants)
        session["barbarian_shout_rounds_remaining"] = 0
        
        total_xp = 0
        for monster in session.get("monsters", []):
            # XP scales quadratically with monster level (level^2)
            monster_level = int(monster.get("level", 1))
            xp_from_monster = monster_level * monster_level
            total_xp += xp_from_monster
        
        # Check if a Monk is in the party for reward doubling
        has_monk = False
        for user in participants:
            user_data = self.state.get_user(user)
            if user_data.get("class_name") == "Monk":
                has_monk = True
                break
        
        reward_multiplier = 2 if has_monk else 1
        if has_monk:
            self._log_event("Monk blessing active: All rewards doubled!", battle=True)
            await self._send_battle_message("Monk blessing active: All rewards are DOUBLED!")
        
        # Collect loot for each participant before applying it
        loot_summary_data = []
        
        # --- XP Totem Bonus Logic ---
        totems = session.get("totems", [])
        # Map: username -> highest XP bonus from their alive XP totem(s)
        xp_totem_bonus = {}
        for t in totems:
            if t.get("alive") and t.get("buff_type") == "xp_buff" and t.get("owner"):
                owner = t["owner"].lower()
                bonus = int(t.get("xp_bonus", 0))
                if bonus > 0:
                    xp_totem_bonus[owner] = max(bonus, xp_totem_bonus.get(owner, 0))
    
        for user in participants:
            user_data = self.state.get_user(user)
            user_data["hop_goldrpg_ready"] = False
            # Award XP from monsters + 1 XP per action taken in this battle
            actions_count = session.get("turn_action_counts", {}).get(user, 0)
            base_xp_earned = (total_xp * reward_multiplier) + actions_count
            # Apply XP totem bonus if user has an alive XP totem
            bonus_pct = xp_totem_bonus.get(user.lower(), 0)
            if bonus_pct > 0:
                xp_earned = int(base_xp_earned * (1 + bonus_pct / 100))
                self._log_event(f"XP Totem: @{user} received +{bonus_pct}% XP bonus ({base_xp_earned} -> {xp_earned})", battle=True)
            else:
                xp_earned = base_xp_earned
            user_data["xp"] = int(user_data.get("xp", 0)) + xp_earned
            if self._is_user_revenant(user_data):
                session["revenant_class_xp"] = int(user_data.get("xp", 0))
    
            # Check for level-ups after XP is awarded
            await self._check_for_levelup(user, user_data)
    
            # Award base gacha tokens
            gacha_tokens_earned = reward_multiplier  # Base victory bonus (multiplied)
            user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + gacha_tokens_earned
            tokens_earned = 0
            entries_earned = 0
            ultra_entries_earned = 0
    
            if random.random() < GACHA_TOKEN_DROP_CHANCE:
                gacha_tokens_earned += reward_multiplier
                user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + reward_multiplier
    
            if random.random() < TOKEN_DROP_CHANCE:
                tokens_earned = reward_multiplier
                user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + tokens_earned
    
            if random.random() < ENTRY_DROP_CHANCE:
                entries_earned = reward_multiplier
                raffle_cog = self._get_raffle_cog()
                if raffle_cog:
                    raffle_cog.state.add_entries(user, entries_earned)
    
            if random.random() < ULTRA_ENTRY_DROP_CHANCE:
                ultra_entries_earned = random.randint(1, 3) * reward_multiplier
                raffle_cog = self._get_raffle_cog()
                if raffle_cog:
                    raffle_cog.state.add_entries(user, ultra_entries_earned)
    
            # Apply referral gacha bonus (per battle)
            referral_bonus = int(user_data.get("referral_bonus_gacha", 0))
            if referral_bonus > 0:
                gacha_tokens_earned += referral_bonus
                user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + referral_bonus
    
            # Track loot for summary
            loot_summary_data.append({
                "name": user,
                "gacha_tokens": gacha_tokens_earned,
                "tokens": tokens_earned,
                "entries": entries_earned,
                "ultra_entries": ultra_entries_earned,
                "xp": xp_earned,
            })
    
        # Award top DPS and top healing (ties allowed)
        top_dps = []
        top_heal = []
        max_damage = 0
        max_heal = 0
        stat_rows = []
        baseline_map = session.get("battle_stat_baseline", {})
        battle_stats = {}
        for user in participants:
            user_data = self.state.get_user(user)
            baseline = baseline_map.get(user, {})
            baseline_damage = int(baseline.get("damage", int(user_data.get("damage_done", 0))))
            baseline_healing = int(baseline.get("healing", int(user_data.get("healing_done", 0))))
            damage_done = max(0, int(user_data.get("damage_done", 0)) - baseline_damage)
            healing_done = max(0, int(user_data.get("healing_done", 0)) - baseline_healing)
            battle_stats[user] = {
                "damage": damage_done,
                "healing": healing_done,
            }
            stat_rows.append({
                "name": user,
                "damage": damage_done,
                "healing": healing_done,
            })
            if damage_done > max_damage:
                max_damage = damage_done
                top_dps = [user]
            elif damage_done == max_damage and damage_done > 0:
                top_dps.append(user)
            if healing_done > max_heal:
                max_heal = healing_done
                top_heal = [user]
            elif healing_done == max_heal and healing_done > 0:
                top_heal.append(user)
    
        if top_dps:
            for user in top_dps:
                user_data = self.state.get_user(user)
                user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + 1
            self._log_event(f"Top DPS: {', '.join(top_dps)} (+1 gacha token each).", battle=True)
            await self._send_battle_message(f"Top DPS: {', '.join(top_dps)} (+1 gacha token).")
    
        if top_heal:
            for user in top_heal:
                user_data = self.state.get_user(user)
                user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + 1
            self._log_event(f"Top Healing: {', '.join(top_heal)} (+1 gacha token each).", battle=True)
            await self._send_battle_message(f"Top Healing: {', '.join(top_heal)} (+1 gacha token).")
    
        top_dps_rankings = sorted(
            stat_rows,
            key=lambda row: (-int(row.get("damage", 0)), str(row.get("name", ""))),
        )[:3]
        top_heal_rankings = sorted(
            stat_rows,
            key=lambda row: (-int(row.get("healing", 0)), str(row.get("name", ""))),
        )[:3]
    
        debug_stat_rows = ", ".join(
            f"@{row.get('name', '?')}: dmg={int(row.get('damage', 0))}, heal={int(row.get('healing', 0))}"
            for row in stat_rows
        )
        logging.info(
            "Battle stat deltas | stream_id=%s | battle_id=%s | %s",
            session.get("stream_id"),
            session.get("battle_id"),
            debug_stat_rows or "no participants",
        )
        
        # Build ascend progress for Derp Clones
        ascend_progress = []
        for user in participants:
            user_data = self.state.get_user(user)
            if user_data.get("class_name") == "Derp Clone" or (user_data.get("class_name") is None and user_data.get("active_player")):
                damage = int(battle_stats.get(user, {}).get("damage", 0))
                ascend_progress.append({
                    "name": user,
                    "current": damage,
                    "threshold": DERP_CLONE_ASCEND_THRESHOLD,
                })
        
        session["battle_active"] = False
        session["battle_id"] = None
        session["monsters"] = []
        session["phase"] = "idle"
        session["action_window_end"] = None
        session["join_window_end"] = None
        session["participants"] = []
        session["action_queue"] = []
        session["buff_pets"] = []
        session["battle_stat_baseline"] = {}
        
        # Log individual rewards for each player
        for loot in loot_summary_data:
            reward_items = []
            if loot["gacha_tokens"] > 0:
                reward_items.append(f"{loot['gacha_tokens']} gacha tokens")
            if loot["tokens"] > 0:
                reward_items.append(f"{loot['tokens']} tokens")
            if loot["entries"] > 0:
                reward_items.append(f"{loot['entries']} entries")
            if loot.get("ultra_entries", 0) > 0:
                reward_items.append(f"{loot['ultra_entries']} ULTRA entries")
            reward_items.append(f"{loot['xp']} XP")
            
            reward_string = ", ".join(reward_items)
            self._log_event(f"Loot: @{loot['name']} earned {reward_string}.", battle=True)
        self.state.save_state()
        self._broadcast_state()
        
        # Broadcast loot summary to overlay - with full error logging
        party_total_xp = sum(int(item.get("xp", 0)) for item in loot_summary_data)
        loot_summary = {
            "type": "rpg_loot_summary",
            "loot": loot_summary_data,
            "ascend_progress": ascend_progress,
            "top_dps": top_dps,
            "top_heal": top_heal,
            "top_dps_rankings": top_dps_rankings,
            "top_heal_rankings": top_heal_rankings,
            "party_total_xp": party_total_xp,
        }
        logging.info(f"Broadcasting loot summary: {len(loot_summary_data)} players, {len(ascend_progress)} with ascend progress")
        logging.debug(f"Loot summary data: {loot_summary}")
        try:
            await broadcast_overlay_message(loot_summary)
            logging.info("Loot summary broadcast completed successfully")
        except Exception as e:
            logging.error(f"Failed to broadcast loot summary: {e}", exc_info=True)
    
    # TODO: Remove unused helper (commented out): _award_harvest_gacha_token
    # async def _award_harvest_gacha_token(self):
    #     session = self.state.session()
    #     participants = session.get("participants", [])
    #     if not participants:
    #         return
    #     target = random.choice(participants)
    #     user_data = self.state.get_user(target)
    #     user_data["class_change_tokens"] = int(user_data.get("class_change_tokens", 0)) + 1
    #     self._log_event(f"Harvest reward: @{target} gains 1 gacha token.", battle=True)
    
    def _consume_revenant_use(self, user: dict) -> bool:
        remaining = int(user.get("revenant_remaining_uses", 0))
        if remaining <= 0:
            return False
        user["revenant_remaining_uses"] = remaining - 1
        return True
    
    def _parse_target(self, arg: str) -> str:
        return arg.lstrip("@").lower()
    
    def _extract_referrer_name(self, referrer_parts: tuple[str, ...]) -> str | None:
        if not referrer_parts:
            return None
        for part in reversed(referrer_parts):
            if part.startswith("@"):
                return part
        return referrer_parts[0]
    
    def _find_close_username(self, raw_name: str) -> str | None:
        if not raw_name:
            return None
        candidates = list(self.state.state.get("users", {}).keys())
        if not candidates:
            return None
        name = self._parse_target(raw_name)
        matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.7)
        return matches[0] if matches else None
    
    def _award_referral(self, new_username: str, referrer: str) -> bool:
        new_user = self.state.get_user(new_username)
        if new_user.get("referral_awarded"):
            return False
        referrer_user = self.state.get_user(referrer)
        referrer_user["referral_bonus_damage"] = int(referrer_user.get("referral_bonus_damage", 0)) + 1
        referrer_user["referral_bonus_gacha"] = int(referrer_user.get("referral_bonus_gacha", 0)) + 1
        referrer_user["class_change_tokens"] = int(referrer_user.get("class_change_tokens", 0)) + REFERRAL_GACHA_TOKENS
        raffle_cog = self._get_raffle_cog()
        if raffle_cog:
            raffle_cog.state.add_entries(referrer, REFERRAL_ENTRIES)
        new_user["referral_awarded"] = True
        new_user["referral_referrer"] = referrer
        self._log_event(
            f"Referral: @{new_username} credited @{referrer} (+{REFERRAL_GACHA_TOKENS} gacha, +{REFERRAL_ENTRIES} entries, +1 dmg bonus, +1 gacha bonus)."
        )
        self.state.save_state()
        self._broadcast_state()
        return True
    
    def _add_pending_referral(self, new_username: str, requested: str, suggestion: str | None):
        pending = self.state.state.setdefault("pending_referrals", [])
        pending.append({
            "new_user": new_username,
            "requested": requested,
            "suggestion": suggestion,
            "ts": _utc_iso(),
        })
        self.state.save_state()
    
    # embark command removed; join now handles activation and salary
    
    @commands.command(name="passrevenant")
    async def passrevenant(self, ctx, target_user: str = None):
        username = ctx.author.name.lower()
        if not target_user:
            await ctx.send("Usage: !passrevenant @username")
            return
    
        self._enforce_single_revenant()
        active = self._get_active_revenant_username()
        if active != username:
            await ctx.send("Only the current Revenant holder can pass the class.")
            return
    
        target = self._parse_target(target_user)
        passed, message = self._transfer_revenant(username, target)
        await ctx.send(message)
        if passed:
            self._broadcast_state()
    
    @commands.command(name="resolvereferral")
    @mod_only
    async def resolvereferral(self, ctx, new_user: str = None, referrer: str = None):
        if not new_user or not referrer:
            await ctx.send("Usage: !resolvereferral <new_user> <referrer>")
            return
        new_username = self._parse_target(new_user)
        referrer_name = self._parse_target(referrer)
        users = self.state.state.get("users", {})
        if new_username not in users:
            await ctx.send(f"Unknown new user: @{new_username}.")
            return
        if referrer_name not in users:
            await ctx.send(f"Unknown referrer: @{referrer_name}.")
            return
        if new_username == referrer_name:
            await ctx.send("Referral invalid: user cannot refer themselves.")
            return
        if self._award_referral(new_username, referrer_name):
            pending = self.state.state.setdefault("pending_referrals", [])
            self.state.state["pending_referrals"] = [
                entry for entry in pending if entry.get("new_user") != new_username
            ]
            self.state.save_state()
            await ctx.send(
                f"Referral resolved: @{referrer_name} gets +{REFERRAL_GACHA_TOKENS} gacha tokens and +{REFERRAL_ENTRIES} entries."
            )
        else:
            await ctx.send("Referral already awarded for that user.")
    
    @commands.command(name="skills")
    async def skills(self, ctx):
        await self._auto_media_for_command(ctx, "skills")
        state_obj = self._state_obj()
        if state_obj is None:
            await ctx.send("RPG state unavailable; try !reloadrpg.")
            return
        username = ctx.author.name.lower()
        self.logger.info("[RPG] skills invoked user=%s", username)
        user = state_obj.get_user(username)
        if user.get("is_revenant"):
            class_name = "Revenant"
            base_name = user.get("previous_class") or user.get("base_class") or "Derp Clone"
            class_display = f"{class_name} (base: {base_name})"
        else:
            class_name = user.get("class_name", "Derp Clone")
            class_display = class_name
        self.logger.info(
            "[RPG] skills user=%s class=%s revenant=%s active=%s",
            username,
            class_name,
            bool(user.get("is_revenant")),
            bool(user.get("active_player")),
        )
        
        # Build skill message dynamically
        msg_parts = [f"@{username} Class: {class_display}"]
        
        # Stream skills
        stream_skill = CLASS_STREAM_SKILLS.get(class_name)
        if stream_skill:
            msg_parts.append(f"Stream: {stream_skill}")
        
        # Battle/Monster skills
        if class_name == "Warlock":
            msg_parts.append("Battle: corruption, sb")
        elif class_name == "Revenant":
            msg_parts.append("Battle: reap, harvest, doom")
        elif class_name == "Khajiit":
            msg_parts.append("Battle: scratch, hairball, meow")
        elif class_name == "Archangel":
            msg_parts.append("Battle: pray, touch, expel, judgement")
        elif class_name == "Alchemist":
            msg_parts.append("Battle: brew, bottle")
        elif class_name == "Meatwad":
            current_form = user.get("meatwad_form")
            if current_form:
                form_name = current_form.get("name", "None")
                msg_parts.append(f"Battle: gun, transform, crack | Current form: {form_name}")
            else:
                msg_parts.append("Battle: gun, transform, crack")
        elif class_name == "Deputy":
            msg_parts.append("Battle: tazer, teargass, donut, tommygun")
        elif class_name == "Barbarian":
            msg_parts.append("Battle: cleave, shout, whirlwind")
        elif class_name == "Buff":
            msg_parts.append("Battle: kid, franklin, jdam, nuke")
        elif class_name == "Enforcer":
            skills = _get_enforcer_skills(user.get("player_level", 1))
            if skills:
                msg_parts.append(f"Battle: {', '.join(skills)}")
        else:
            monster_skill = CLASS_MONSTER_SKILLS.get(class_name)
            if monster_skill and monster_skill[0] != "none":
                msg_parts.append(f"Battle: {monster_skill[0]}")
        
        # Party skills
        party_skills = []
        if class_name == "Healer":
            party_skills.append("heal")
        elif class_name == "Warrior":
            party_skills.append("taunt")
        elif class_name == "Monk":
            party_skills.append("ohm")
        elif class_name == "Revenant":
            party_skills.extend(["summon", "doom"])
        elif class_name == "Streamer":
            # Add dropship to battle skills for Streamer
            msg_parts.append("Battle: dropship")
            party_skills.extend(["heal", "totem", "rez", "gamba"])
        elif class_name == "Warlock":
            party_skills.extend(["summon_imp", "dragon"])
        elif class_name == "Hop":
            party_skills.extend(["sap", "deagle", "c4", "greenarrow", "goldrpg"])
        elif class_name == "Deputy":
            party_skills.extend(["tazer", "teargass", "donut", "tommygun"])
        elif class_name == "Barbarian":
            party_skills.extend(["cleave", "shout", "whirlwind"])
        elif class_name == "Alchemist":
            party_skills.extend(["brew", "bottle"])
        elif class_name == "Buff":
            party_skills.extend(["kid", "franklin", "jdam", "nuke"])
        
        if party_skills:
            msg_parts.append(f"Party: {', '.join(party_skills)}")
        
        await ctx.send(" | ".join(msg_parts))
    
    @commands.command(name="ascend")
    async def ascend(self, ctx, class_name: str = None):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        previous_tier = int(user.get("class_tier", 0))
        current_class = str(user.get("class_name", "Derp Clone")).strip()
        if user.get("is_revenant"):
            await ctx.send("You cannot ascend while a mythic class is active.")
            return
        if not class_name:
            if previous_tier == 1 and current_class == "Warrior":
                await ctx.send("Choose your path: !ascend barbarian")
            else:
                await ctx.send("Choose your path: !ascend warrior | rogue | mage | healer | monk")
            return
        class_name = class_name.strip().capitalize()
        if previous_tier == 1:
            if current_class != "Warrior" or class_name != "Barbarian":
                await ctx.send("You have already ascended.")
                return
    
            warrior_level = self._get_level_from_xp(int(user.get("xp", 0)), user)
            if warrior_level < BASE_CLASS_LEVEL_CAP:
                await ctx.send(
                    f"Barbarian requires Warrior level {BASE_CLASS_LEVEL_CAP}. You are level {warrior_level}."
                )
                return
    
            user["class_name"] = "Barbarian"
            user["class_tier"] = 2
            user["base_class"] = "Barbarian"
            user["barbarian_whirlwind_cooldown"] = 0
            # XP/level reset for ascended class
            user["xp"] = 0
            user["player_level"] = 1
            user["hp_max"] = self.state._calculate_max_hp(user)
            user["hp_current"] = user["hp_max"]
    
            diff_gacha_tokens, diff_entries = self._grant_salary_diff(username, previous_tier)
            self.state.save_state()
            self._log_event(f"Ascension: @{username} became Barbarian.")
            if diff_gacha_tokens or diff_entries:
                await ctx.send(
                    f"@{username} has ascended to Barbarian! Promotion bonus: +{diff_gacha_tokens} gacha tokens, +{diff_entries} entries."
                )
            else:
                await ctx.send(f"@{username} has ascended to Barbarian.")
            self._broadcast_state()
            return
    
        if previous_tier > 0:
            await ctx.send("You have already ascended.")
            return
    
        if class_name not in BASE_CLASSES:
            await ctx.send("Choose your path: !ascend warrior | rogue | mage | healer | monk")
            return
        
        # Check if attempting Monk (requires 1M XP)
        if class_name == "Monk":
            if int(user.get("xp", 0)) < MONK_XP_THRESHOLD:
                remaining = MONK_XP_THRESHOLD - int(user.get("xp", 0))
                await ctx.send(f"You need {MONK_XP_THRESHOLD:,} XP to become a Monk. You need {remaining:,} more.")
                return
        else:
            # Standard tier-1 classes (Derp Clone) need damage threshold
            if int(user.get("lifetime_monster_damage", 0)) < DERP_CLONE_ASCEND_THRESHOLD:
                await ctx.send(f"You need {DERP_CLONE_ASCEND_THRESHOLD} lifetime monster damage to ascend.")
                return
        
        new_class = class_name
        user["class_name"] = new_class
        user["class_tier"] = 1
        user["base_class"] = new_class
        # XP/level reset for Alchemist ascension
        if new_class == "Alchemist":
            user["xp"] = 0
            user["player_level"] = 1
        # Update HP for new class tier
        user["hp_max"] = self.state._calculate_max_hp(user)
        user["hp_current"] = user["hp_max"]
        # Reset ascension stats when they ascend
        user["damage_done"] = 0
        user["killing_blows"] = 0
        user["times_knocked_out"] = 0
    
        diff_gacha_tokens, diff_entries = self._grant_salary_diff(username, previous_tier)
        self.state.save_state()
        self._log_event(f"Ascension: @{username} became {new_class}.")
        if diff_gacha_tokens or diff_entries:
            await ctx.send(
                f"@{username} has ascended to {new_class}! Promotion bonus: +{diff_gacha_tokens} gacha tokens, +{diff_entries} entries."
            )
        else:
            await ctx.send(f"@{username} has ascended to {new_class}.")
        self._broadcast_state()
    
    @commands.command(name="bonk")
    async def bonk(self, ctx, target_index: str = None):
        self.logger.info("[RPG] bonk invoked by %s target=%s", ctx.author.name.lower(), target_index)
        try:
            await self._queue_monster_action(
                ctx,
                "bonk",
                1,
                required_class="Derp Clone",
                target_index=target_index,
                allow_media_fallback=True,
                silent_on_class_mismatch=True,
            )
        except Exception:
            self.logger.exception("[RPG] bonk failed", exc_info=True)
            try:
                await ctx.send("Bonk failed: unexpected error.")
            except Exception:
                pass
    
    @commands.command(name="strike")
    async def strike(self, ctx, target_index: str = None):
        await self._queue_monster_action(
            ctx,
            "strike",
            5,
            required_class="Warrior",
            target_index=target_index,
            allow_media_fallback=True,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="cleave")
    async def cleave(self, ctx, target_index: str = None):
        await self._queue_monster_action(
            ctx,
            "cleave",
            BARBARIAN_CLEAVE_BASE_DAMAGE,
            required_class="Barbarian",
            target_index=target_index,
            allow_media_fallback=True,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="shout")
    async def shout(self, ctx):
        username = ctx.author.name.lower()
        await self._maybe_trigger_media("shout", ctx)
        user = self.state.get_user(username)
        session = self.state.session()
    
        if str(user.get("class_name", "")).strip().lower() != "barbarian" or user.get("is_revenant"):
            return
    
        barbarian_level = self._get_level_from_xp(int(user.get("xp", 0)), user)
        if barbarian_level < BARBARIAN_SHOUT_UNLOCK_LEVEL:
            await ctx.send(
                f"Shout unlocks at Barbarian level {BARBARIAN_SHOUT_UNLOCK_LEVEL}. You are level {barbarian_level}."
            )
            return
    
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "barbarian_shout",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self._log_event(f"Queued: @{username} used shout.", battle=True)
        await ctx.send(f"@{username} queued SHOUT.")
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="whirlwind")
    async def whirlwind(self, ctx):
        username = ctx.author.name.lower()
        await self._play_media_fallback("whirlwind", ctx)
        user = self.state.get_user(username)
        session = self.state.session()
    
        if str(user.get("class_name", "")).strip().lower() != "barbarian" or user.get("is_revenant"):
            return
    
        barbarian_level = self._get_level_from_xp(int(user.get("xp", 0)), user)
        if barbarian_level < BARBARIAN_WHIRLWIND_UNLOCK_LEVEL:
            await ctx.send(
                f"Whirlwind unlocks at Barbarian level {BARBARIAN_WHIRLWIND_UNLOCK_LEVEL}. You are level {barbarian_level}."
            )
            return
    
        if int(user.get("barbarian_whirlwind_cooldown", 0)) > 0:
            await ctx.send(
                f"Whirlwind cooldown: {int(user.get('barbarian_whirlwind_cooldown', 0))} turns remaining."
            )
            return
    
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "whirlwind",
            "damage": BARBARIAN_WHIRLWIND_BASE_DAMAGE,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self._log_event(f"Queued: @{username} used whirlwind.", battle=True)
        await ctx.send(f"@{username} queued WHIRLWIND.")
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="backstab")
    async def backstab(self, ctx, target_index: str = None):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("backstab", ctx)
        if not user.get("active_player"):
            return
        class_name = user.get("class_name", "Derp Clone")
        # Allow both Rogue and Hop to use backstab
        if class_name not in ["Rogue", "Hop"]:
            return
        await self._queue_monster_action(
            ctx,
            "backstab",
            4,
            required_class=class_name,
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="bolt")
    async def bolt(self, ctx, target_index: str = None):
        await self._queue_monster_action(
            ctx,
            "bolt",
            6,
            required_class="Mage",
            target_index=target_index,
            allow_media_fallback=True,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="smite")
    async def smite(self, ctx, target_index: str = None):
        await self._queue_monster_action(
            ctx,
            "smite",
            4,
            required_class="Healer",
            target_index=target_index,
            allow_media_fallback=True,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="heal")
    async def heal(self, ctx, target_num: str = None):
        username = ctx.author.name.lower()
        # _state_obj is defined on the cog, not the state; guard against state-only binding
        state_obj = getattr(self, "_state_obj", None)
        if callable(state_obj):
            state_obj = state_obj()
        else:
            state_obj = None
        if state_obj is None:
            self.logger.warning("[RPG] _queue_monster_action missing state for %s", username)
            await ctx.send("RPG state unavailable; try !reloadrpg.")
            return

        user = state_obj.get_user(username)
        session = state_obj.session()
        class_name = str(user.get("class_name", "")).strip()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        is_streamer_heal = username == STREAMER_NAME.lower() and class_name == "Streamer"
        is_healer_heal = class_name == "Healer"
    
        if not is_healer_heal and not is_streamer_heal:
            await ctx.send("Only Healers and the Streamer can use heal.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Parse target number (1-indexed for party members)
        target_party_index = None
        if target_num and not is_streamer_heal:
            try:
                target_party_index = int(target_num) - 1  # Convert to 0-indexed
                if target_party_index < 0 or target_party_index >= len(participants):
                    await ctx.send(f"Invalid party member. Use a number 1-{len(participants)}.")
                    return
            except ValueError:
                await ctx.send("Invalid target. Use !heal or !heal <number>")
                return
        elif target_num and is_streamer_heal:
            await ctx.send("Streamer heal is party-wide. Use !heal with no target.")
            return
        
        # Queue heal action
        action_name = "stream_heal" if is_streamer_heal else "heal"
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": action_name,
            "damage": 0,  # Will be determined during resolution
            "target_index": None,
            "target_party_index": target_party_index,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        if is_streamer_heal:
            self._log_event(f"Queued: @{username} queued party heal.", battle=True)
            await ctx.send(f"@{username} queued party heal.")
        else:
            target_note = f" on party member {target_party_index + 1}" if target_party_index is not None else ""
            self._log_event(f"Queued: @{username} heal{target_note}.", battle=True)
            await ctx.send(f"@{username} queued heal{target_note}.")
        media_cog = self.bot.get_cog("MediaOverlayCog")
        if media_cog:
            await media_cog.play_media_command("heal", ctx)
        self._broadcast_state()
        
        # Check if all alive players have acted
        action_queue = session.get("action_queue", [])
        queued_users = {entry.get("user") for entry in action_queue}
        alive_participants = self._get_alive_participants(session)
        if alive_participants and all(user in queued_users for user in alive_participants):
            await self._resolve_turn()
    
    @commands.command(name="ohm")
    async def ohm(self, ctx):
        """Monk skill: Enter a meditative state. Does nothing but counts as action."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if user.get("class_name") != "Monk":
            await ctx.send("Only Monks can meditate with ohm.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Queue ohm action (does nothing but counts as action)
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "ohm",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self._log_event(f"Queued: @{username} meditated with ohm.", battle=True)
        await ctx.send(f"@{username} enters a meditative state and radiates blessing energy...")
        self._broadcast_state()
        
        # Check if all alive players have acted
        action_queue = session.get("action_queue", [])
        queued_users = {entry.get("user") for entry in action_queue}
        alive_participants = self._get_alive_participants(session)
        if alive_participants and all(user in queued_users for user in alive_participants):
            await self._resolve_turn()
    
    
    @commands.command(name="taunt")
    async def taunt(self, ctx):
        """Warrior skill: Force monsters to attack this warrior."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        session = self.state.session()
    
        await self._play_media_fallback("taunt", ctx)
    
        if not user.get("active_player"):
            return
        if self._is_user_revenant(user):
            return
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            return
        
        current_class = str(user.get("class_name", "")).strip()
        base_class = str(user.get("base_class", "")).strip()
        is_warrior = current_class.lower() == "warrior" or base_class.lower() == "warrior"
        if not is_warrior:
            return
        if not session.get("battle_active"):
            return
        if session.get("phase") != "action":
            return
        participants = session.setdefault("participants", [])
        if username not in participants:
            return
        action_queue = session.get("action_queue", [])
        existing_entry = next((entry for entry in action_queue if entry.get("user") == username), None)
    
        if existing_entry:
            previous_action = str(existing_entry.get("action", "action"))
            existing_entry["action"] = "taunt"
            existing_entry["damage"] = 0
            existing_entry["target_index"] = None
            existing_entry["ts"] = _now_ts()
            action_msg = f"@{username} switched from {previous_action} to taunt and forced enemies to attack!"
            log_msg = f"Queued: @{username} switched from {previous_action} to taunt."
        else:
            session.setdefault("action_queue", []).append({
                "user": username,
                "action": "taunt",
                "damage": 0,
                "target_index": None,
                "ts": _now_ts(),
            })
            action_msg = f"@{username} taunted and forced enemies to attack!"
            log_msg = f"Queued: @{username} taunted."
        
        self.state.save_state()
        self._log_event(log_msg, battle=True)
        await ctx.send(action_msg)
        self._broadcast_state()
        
        # Check if all alive players have acted
        action_queue = session.get("action_queue", [])
        queued_users = {entry.get("user") for entry in action_queue}
        alive_participants = self._get_alive_participants(session)
        if alive_participants and all(user in queued_users for user in alive_participants):
            await self._resolve_turn()
    
    @commands.command(name="reap")
    async def reap(self, ctx, target_index: str = None):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        revenant_level = self._get_level_from_xp(int(user.get("xp", 0)), user)
        reap_damage = REAP_BASE_DAMAGE + (max(0, revenant_level - 1) * REAP_DAMAGE_PER_LEVEL)
        reap_damage = min(REAP_MAX_BASE_DAMAGE, reap_damage)
        await self._queue_monster_action(
            ctx,
            "reap",
            reap_damage,
            required_class="Revenant",
            consume_revenant=False,
            target_index=target_index,
            allow_media_fallback=True,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="harvest")
    async def harvest(self, ctx, target_index: str = None):
        await self._queue_monster_action(
            ctx,
            "harvest",
            10,
            required_class="Revenant",
            consume_revenant=False,
            target_index=target_index,
            allow_media_fallback=True,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="summon")
    async def summon(self, ctx, pet_type: str = None):
        """Revenant skill: Summon a random undead pet (max 3 active)."""
        self.logger.info("[RPG] summon invoked by %s pet_type=%s", ctx.author.name.lower(), pet_type)
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("summon", ctx)
        session = self.state.session()
    
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            return
        if not user.get("is_revenant"):
            return
        if not user.get("active_player"):
            return
        if not session.get("battle_active"):
            return
        if session.get("phase") != "action":
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            return
    
        undead_pets = session.setdefault("undead_pets", [])
        active_pets = [p for p in undead_pets if p.get("owner") == username and p.get("alive")]
        if len(active_pets) >= REVENANT_UNDEAD_MAX:
            await ctx.send(f"You already have {REVENANT_UNDEAD_MAX} undead active.")
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        selected = str(pet_type or "").strip().lower()
        if selected:
            alias_map = {
                "blob": "blob",
                "ghoul": "ghoul",
                "wisp": "wisp",
                "b": "blob",
                "g": "ghoul",
                "w": "wisp",
            }
            summoned_type = alias_map.get(selected)
            if not summoned_type:
                await ctx.send("Usage: !summon [blob|ghoul|wisp]")
                return
        else:
            summoned_type = random.choice(["blob", "ghoul", "wisp"])
    
        revenant_level = max(1, self._get_level_from_xp(int(user.get("xp", 0)), user))
        pet_id = f"undead_{summoned_type}_{username}_{_now_ts()}"
        if summoned_type == "blob":
            blob_hp = REVENANT_BLOB_BASE_HP + ((revenant_level - 1) * REVENANT_BLOB_HP_PER_LEVEL)
            pet_data = {
                "id": pet_id,
                "owner": username,
                "pet_type": "blob",
                "alive": True,
                "hp": blob_hp,
                "max_hp": blob_hp,
                "damage": REVENANT_BLOB_DAMAGE,
                "mitigation": REVENANT_BLOB_MITIGATION,
            }
            summon_text = "Blob"
        elif summoned_type == "ghoul":
            ghoul_hp = REVENANT_GHOUL_BASE_HP + ((revenant_level - 1) * REVENANT_GHOUL_HP_PER_LEVEL)
            pet_data = {
                "id": pet_id,
                "owner": username,
                "pet_type": "ghoul",
                "alive": True,
                "hp": ghoul_hp,
                "max_hp": ghoul_hp,
                "damage": REVENANT_GHOUL_DAMAGE,
                "crit_chance": REVENANT_GHOUL_CRIT_CHANCE,
            }
            summon_text = "Ghoul"
        else:
            wisp_hp = REVENANT_WISP_BASE_HP + ((revenant_level - 1) * REVENANT_WISP_HP_PER_LEVEL)
            pet_data = {
                "id": pet_id,
                "owner": username,
                "pet_type": "wisp",
                "alive": True,
                "hp": wisp_hp,
                "max_hp": wisp_hp,
                "energy": 0,
                "rez_cooldown": 0,
            }
            summon_text = "Wisp"
    
        undead_pets.append(pet_data)
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "summon_undead",
            "damage": 0,
            "target_index": None,
            "summoned_type": summoned_type,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self._log_event(f"Queued: @{username} summoned {summon_text}.", battle=True)
        await ctx.send(f"@{username} summoned {summon_text}!")
        self._broadcast_state()
    
        action_queue = session.get("action_queue", [])
        queued_users = {entry.get("user") for entry in action_queue}
        alive_participants = self._get_alive_participants(session)
        if alive_participants and all(user in queued_users for user in alive_participants):
            await self._resolve_turn()
    
    async def _queue_monster_action(
        self,
        ctx,
        action: str,
        damage: int,
        required_class: str,
        consume_revenant: bool = False,
        target_index: str = None,
        allow_media_fallback: bool = False,
        silent_on_class_mismatch: bool = False,
    ):
        username = ctx.author.name.lower()
        self.logger.info(
            "[RPG] queue_entry user=%s action=%s target_raw=%s", username, action, target_index
        )
        state_obj = self._state_obj()
        if state_obj is None:
            self.logger.warning("[RPG] _queue_monster_action missing state for %s", username)
            if allow_media_fallback:
                return
            await ctx.send("RPG state unavailable; try !reloadrpg.")
            return

        user = state_obj.get_user(username)
        session = state_obj.session()
    
        if allow_media_fallback:
            await self._maybe_trigger_media(action, ctx)

        # If no active battle, allow SFX fallback and exit quietly
        if not session.get("battle_active"):
            self.logger.info("[RPG] %s blocked for %s: no battle active", action, username)
            return

        # If joined mid-turn, defer actions until next turn
        join_turns = session.get("joined_turns", {})
        joined_turn = join_turns.get(username)
        current_turn = int(session.get("turn_number", 0))
        if joined_turn is not None:
            if current_turn <= joined_turn and session.get("phase") == "action":
                self.logger.info("[RPG] %s blocked for %s: joined mid-turn %s", action, username, joined_turn)
                await ctx.send("You joined mid-turn; you can act next action window.")
                return
            else:
                join_turns.pop(username, None)
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            self.logger.info("[RPG] %s blocked for %s: knocked out", action, username)
            if allow_media_fallback:
                return
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            self.logger.info("[RPG] %s blocked for %s: not active", action, username)
            if allow_media_fallback:
                return
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            self.logger.info("[RPG] %s blocked for %s: no battle", action, username)
            if allow_media_fallback:
                return
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            self.logger.info("[RPG] %s blocked for %s: phase=%s", action, username, session.get("phase"))
            if allow_media_fallback:
                return
            await ctx.send("Action window is closed.")
            return
        if required_class == "Revenant" and not user.get("is_revenant"):
            if silent_on_class_mismatch:
                if allow_media_fallback:
                    return
                return
            await ctx.send("You cannot use that command.")
            return
        if required_class != "Revenant" and user.get("class_name") != required_class:
            if silent_on_class_mismatch:
                if allow_media_fallback:
                    return
                return
            await ctx.send(f"Only {required_class} can use this.")
            return
        participants = session.setdefault("participants", [])
        if username not in participants:
            if allow_media_fallback:
                return
            await ctx.send("You must !join before acting.")
            return
        alive_monsters = [m for m in session.get("monsters", []) if m.get("alive")]
        self.logger.info(
            "[RPG] action queued user=%s action=%s target=%s phase=%s turn=%s queued=%s",
            username,
            action,
            target_index,
            session.get("phase"),
            session.get("turn_number"),
            len(session.get("action_queue", [])),
        )
        if target_index is not None:
            cleaned = "".join(ch for ch in str(target_index) if ch.isdigit())
            if cleaned == "":
                target_index = None
            else:
                try:
                    target_index = int(cleaned)
                except Exception:
                    await ctx.send("Target must be a monster number like !bonk 1.")
                    return
        if target_index is not None:
            if not self._get_monster_by_index(session, target_index):
                await ctx.send("That monster number is not available.")
                return
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        if consume_revenant and not self._consume_revenant_use(user):
            await ctx.send("No mythic uses remaining.")
            return
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": action,
            "damage": damage,
            "target_index": target_index,
            "ts": _now_ts(),
        })
        self.state.save_state()
        target_note = f" on monster {target_index}" if target_index else ""
        self._log_event(f"Queued: @{username} {action} ({damage}){target_note}.", battle=True)
        if target_index:
            await ctx.send(f"@{username} queued {action} on monster {target_index}.")
        else:
            if len(alive_monsters) > 1:
                await ctx.send(f"@{username} queued {action} (will target lowest HP monster).")
            else:
                await ctx.send(f"@{username} queued {action}.")
        if not allow_media_fallback:
            media_cog = self.bot.get_cog("MediaOverlayCog")
            if media_cog:
                await media_cog.play_media_command(action, ctx)
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    async def _resolve_turn_if_ready(self, session: dict):
        action_queue = session.get("action_queue", [])
        queued_users = {entry.get("user") for entry in action_queue}
        alive_participants = self._get_alive_participants(session)
        self.logger.info(
            "[RPG] resolve_check phase=%s turn=%s queued=%s alive=%s",
            session.get("phase"),
            session.get("turn_number"),
            len(action_queue),
            len(alive_participants),
        )
        if alive_participants and all(user in queued_users for user in alive_participants):
            self.logger.info("[RPG] resolve_trigger phase=%s turn=%s", session.get("phase"), session.get("turn_number"))
            await self._resolve_turn()
    
    # TODO: Remove unused helper (commented out): _is_first_turn_of_battle
    # def _is_first_turn_of_battle(self, session: dict) -> bool:
    #     return int(session.get("turn_number", 0)) <= 1
    
    async def _can_use_buff_command(self, ctx, username: str, user: dict, action_name: str = "buff_action") -> bool:
        class_name = str(user.get("class_name", "")).strip().lower()
        if self._is_user_revenant(user):
            self.logger.info("[RPG] %s blocked for %s: revenant", action_name, username)
            await ctx.send("Revenants cannot use Buff skills.")
            return False
        if username != BUFF_NAME.lower() and class_name != "buff":
            self.logger.info("[RPG] %s blocked for %s: class mismatch (%s)", action_name, username, class_name)
            await ctx.send("Only Buff can use this skill.")
            return False
        return True
    
    async def _validate_buff_turn_rule(self, ctx, action_name: str, session: dict) -> bool:
        return True
    
    @commands.command(name="join")
    async def join(self, ctx, *args: str):
        username = ctx.author.name.lower()
        state_obj = self._state_obj()
        if state_obj is None:
            await ctx.send("RPG state unavailable; try !reloadrpg.")
            return

        users = state_obj.state.get("users", {})
        user_exists = username in users
        user = state_obj.get_user(username)
        now_ts = _now_ts()
        self._enforce_single_revenant()

        # Allow Revenant pass if overdue
        ref_parts = [arg for arg in args if str(arg).lower() != "auto"]
        if self._is_user_revenant(user) and self._is_revenant_pass_due(user, now_ts):
            pass_target_raw = self._extract_referrer_name(ref_parts)
            if not pass_target_raw:
                await ctx.send("Your 7-day Revenant term has ended. Pass it with: !passrevenant @username")
                return
            pass_target = self._parse_target(pass_target_raw)
            passed, pass_message = self._transfer_revenant(username, pass_target)
            await ctx.send(pass_message)
            if not passed:
                return
            user = state_obj.get_user(username)

        join_mode = "auto" if any(str(arg).lower() == "auto" for arg in args) else None
        referrer_raw = self._extract_referrer_name(ref_parts)
        activation_msgs: list[str] = []

        if username == STREAMER_NAME.lower():
            user["active_player"] = True
            state_obj.save_state()
            activation_msgs.append(f"@{username} is always active as Streamer.")
        elif not user.get("active_player"):
            self._reset_daily_log_if_needed(now_ts)
            user["active_player"] = True
            user["daily_embark_ts"] = now_ts
            usage = user.setdefault("stream_usage", {})
            usage.pop("edict", None)
            state_obj.save_state()
            granted, salary_msg = self.grant_salary(username)
            activation_msgs.append(f"@{username} is now active. {salary_msg}")

            if not user_exists:
                activation_msgs.append(f"@{username} begins their journey as a Derp Clone!")
                is_fresh_derp = user.get("class_name") == "Derp Clone" and int(user.get("class_tier", 0)) == 0
                if referrer_raw and is_fresh_derp:
                    referrer_name = self._parse_target(referrer_raw)
                    if referrer_name == username:
                        activation_msgs.append("Referral ignored: you cannot refer yourself.")
                    elif referrer_name in users:
                        if self._award_referral(username, referrer_name):
                            activation_msgs.append(
                                f"Referral bonus: @{referrer_name} gets +{REFERRAL_GACHA_TOKENS} gacha tokens and +{REFERRAL_ENTRIES} entries."
                            )
                    else:
                        suggestion = self._find_close_username(referrer_name)
                        if suggestion == username:
                            suggestion = None
                        self._add_pending_referral(username, referrer_name, suggestion)
                        if suggestion:
                            activation_msgs.append(
                                f"Referral not found. Mods: did you mean @{suggestion}? Use !resolvereferral {username} {suggestion}."
                            )
                        else:
                            activation_msgs.append(
                                f"Referral not found. Mods can resolve with !resolvereferral {username} <referrer>."
                            )
                elif referrer_raw and not is_fresh_derp:
                    activation_msgs.append("Referral ignored: only brand-new Derp Clones can refer someone.")

        session = state_obj.session()
        response_msgs = activation_msgs.copy()

        if not session.get("battle_active"):
            if response_msgs:
                await ctx.send(" ".join(response_msgs))
            else:
                await ctx.send("No active battle to join.")
            self._broadcast_state()
            return

        participants = session.setdefault("participants", [])
        auto_join_modes = session.setdefault("auto_join_modes", {})
        joined_turns = session.setdefault("joined_turns", {})
        baseline_map = session.setdefault("battle_stat_baseline", {})

        if username in participants:
            if join_mode == "auto":
                auto_join_modes[username] = "primary_half"
                response_msgs.append(f"Auto mode enabled for @{username}.")
            elif join_mode is None and username in auto_join_modes:
                auto_join_modes.pop(username, None)
                response_msgs.append(f"Auto mode cleared for @{username}.")
            else:
                response_msgs.append("You have already joined this battle.")
        else:
            user["hp_current"] = int(user.get("hp_max", DEFAULT_PLAYER_HP))
            user["hop_goldrpg_ready"] = False
            user["barbarian_whirlwind_cooldown"] = 0
            user["buff_takeoff_used"] = False
            user["buff_kid_intercept_triggered"] = False
            user["buff_franklin_crit_triggered"] = False
            user["buff_franklin_jdam_buff_triggered"] = False
            user["buff_jdam_crit_triggered"] = False
            user["buff_jdam_forced_crit_charges"] = 0
            if user.get("class_name") == "Archangel":
                user["archangel_power"] = 0
            participants.append(username)

            if username not in baseline_map:
                baseline_map[username] = {
                    "damage": int(user.get("damage_done", 0)),
                    "healing": int(user.get("healing_done", 0)),
                }

            if join_mode == "auto":
                auto_join_modes[username] = "primary_half"
            else:
                auto_join_modes.pop(username, None)

            current_turn = int(session.get("turn_number", 0))
            if session.get("phase") == "action":
                joined_turns[username] = current_turn
            else:
                joined_turns.pop(username, None)

            self._log_event(f"Join: @{username} entered the battle.", battle=True)
            if join_mode == "auto":
                response_msgs.append(f"@{username} joined the fight in AUTO mode (half-strength primary skill if no action is queued).")
            else:
                response_msgs.append(f"@{username} joined the fight.")

        state_obj.save_state()
        self._broadcast_state()
        if response_msgs:
            await ctx.send(" ".join(response_msgs))
    
    @commands.command(name="guard")
    async def guard(self, ctx, target: str = None):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        if user.get("class_name") != "Warrior":
            await ctx.send("Only Warriors can guard.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not target:
            await ctx.send("Usage: !guard @user")
            return
        if user.get("stream_usage", {}).get("guard"):
            await ctx.send("Guard already used this stream.")
            return
        target_user = self.state.get_user(self._parse_target(target))
        target_user["guard_active"] = True
        user.setdefault("stream_usage", {})["guard"] = True
        self.state.save_state()
        self._log_event(f"Guard: @{username} protected @{self._parse_target(target)}.")
        await ctx.send(f"@{username} guarded @{self._parse_target(target)}.")
        self._broadcast_state()
    
    @commands.command(name="pickpocket")
    async def pickpocket(self, ctx, target: str = None):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        if user.get("class_name") != "Rogue":
            await ctx.send("Only Rogues can pickpocket.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not target:
            await ctx.send("Usage: !pickpocket @user")
            return
        if user.get("stream_usage", {}).get("pickpocket"):
            await ctx.send("Pickpocket already used this stream.")
            return
        target_name = self._parse_target(target)
        target_user = self.state.get_user(target_name)
        
        # Check if target has already been stolen from this stream
        if target_user.get("stolen_from"):
            await ctx.send(f"@{target_name} has already been stolen from this stream. Pick another target.")
            user.setdefault("stream_usage", {})["pickpocket"] = True
            self.state.save_state()
            return
        
        if target_user.get("guard_active"):
            target_user["guard_active"] = False
            user.setdefault("stream_usage", {})["pickpocket"] = True
            self.state.save_state()
            self._log_event(f"Pickpocket blocked: @{username} vs @{target_name}.")
            await ctx.send("Pickpocket blocked by guard.")
            return
        success = random.random() < 0.2
        if success:
            # Steal 1 gacha token from target
            target_gacha = int(target_user.get("class_change_tokens", 0))
            if target_gacha > 0:
                target_user["class_change_tokens"] = target_gacha - 1
                user["class_change_tokens"] = int(user.get("class_change_tokens", 0)) + 1
                # Set the stolen_from flag with the amount stolen
                target_user["stolen_from"] = 1
                self._log_event(f"Pickpocket: @{username} stole 1 gacha token from @{target_name}.")
                await ctx.send(f"@{username} stole 1 gacha token from @{target_name}.")
            else:
                self._log_event(f"Pickpocket failed: @{username} vs @{target_name} (no tokens).")
                await ctx.send("Pickpocket failed (target has no gacha tokens).")
        else:
            self._log_event(f"Pickpocket failed: @{username} vs @{target_name}.")
            await ctx.send("Pickpocket failed.")
        user.setdefault("stream_usage", {})["pickpocket"] = True
        self.state.save_state()
        self._broadcast_state()
    
    @commands.command(name="transmute")
    async def transmute(self, ctx):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        if user.get("class_name") != "Mage":
            await ctx.send("Only Mages can transmute.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        usage = user.setdefault("stream_usage", {})
        if usage.get("transmute"):
            await ctx.send("Transmute already used this stream.")
            return
        if usage.get("entry_gain"):
            await ctx.send("Entry gain already used this stream.")
            return
        song_cog = self._get_song_cog()
        raffle_cog = self._get_raffle_cog()
        if not raffle_cog:
            await ctx.send("Transmute unavailable right now.")
            return
        if int(user.get("class_change_tokens", 0)) < 2:
            await ctx.send("Not enough gacha tokens (need 2).")
            return
        user["class_change_tokens"] = int(user.get("class_change_tokens", 0)) - 2
        raffle_cog.state.add_entries(username, 1)
        usage["transmute"] = True
        usage["entry_gain"] = True
        self.state.save_state()
        self._log_event(f"Transmute: @{username} traded 2 gacha tokens for 1 entry.")
        await ctx.send("Transmute complete: +1 entry.")
        self._broadcast_state()
    
    @commands.command(name="restore")
    async def restore(self, ctx, target: str = None, mode: str = None):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        if user.get("class_name") != "Healer":
            await ctx.send("Only Healers can restore.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        usage = user.setdefault("stream_usage", {})
        if usage.get("restore"):
            await ctx.send("Restore already used this stream.")
            return
        if not target:
            await ctx.send("Usage: !restore @user [entry|gacha_tokens]")
            return
        target_name = self._parse_target(target)
        target_user = self.state.get_user(target_name)
        raffle_cog = self._get_raffle_cog()
        if not raffle_cog:
            await ctx.send("Restore unavailable right now.")
            return
        
        # Check if target has been stolen from - if so, restore the stolen amount
        if target_user.get("stolen_from"):
            stolen_amount = target_user.get("stolen_from", 0)
            target_user["class_change_tokens"] = int(target_user.get("class_change_tokens", 0)) + stolen_amount
            target_user["stolen_from"] = None  # Clear the flag
            user["healing_done"] = int(user.get("healing_done", 0)) + stolen_amount
            self._log_event(f"Restore: @{username} restored {stolen_amount} stolen gacha token(s) to @{target_name}.")
            await ctx.send(f"@{username} restored {stolen_amount} stolen gacha token(s) to @{target_name}.")
        elif mode == "entry":
            if usage.get("entry_gain"):
                await ctx.send("Entry gain already used this stream.")
                return
            raffle_cog.state.add_entries(target_name, 1)
            usage["entry_gain"] = True
            user["healing_done"] = int(user.get("healing_done", 0)) + 1
            self._log_event(f"Restore: @{username} restored 1 entry to @{target_name}.")
            await ctx.send(f"Restore complete for @{target_name}.")
        else:
            target_user["class_change_tokens"] = int(target_user.get("class_change_tokens", 0)) + 2
            user["healing_done"] = int(user.get("healing_done", 0)) + 2
            self._log_event(f"Restore: @{username} restored 2 gacha tokens to @{target_name}.")
            await ctx.send(f"Restore complete for @{target_name}.")
        usage["restore"] = True
        self.state.save_state()
        self._broadcast_state()
    
    @commands.command(name="blessing")
    async def blessing(self, ctx):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        if user.get("class_name") != "Monk":
            await ctx.send("Only Monks can use blessing.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        usage = user.setdefault("stream_usage", {})
        if usage.get("blessing"):
            await ctx.send("Blessing already used this stream.")
            return
        raffle_cog = self.bot.get_cog("RaffleCog")
        if not raffle_cog:
            await ctx.send("Blessing unavailable right now.")
            return
        # Trigger raffle +
        raffle_cog.state.increase_multiplier(1)
        usage["blessing"] = True
        self.state.save_state()
        self._log_event(f"Blessing: @{username} increased the giveaway multiplier.")
        await ctx.send(f"@{username} blessed the giveaway with a multiplier boost!")
        self._broadcast_state()
    
    @commands.command(name="edict")
    async def edict(self, ctx):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        if not user.get("is_revenant"):
            await ctx.send("You cannot use that command.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        usage = user.setdefault("stream_usage", {})
        if usage.get("edict"):
            await ctx.send("Edict already used this stream.")
            return
        raffle_cog = self._get_raffle_cog()
        if not raffle_cog:
            await ctx.send("Edict unavailable right now.")
            return
        active_users = [
            name for name, data in self.state.state.get("users", {}).items()
            if data.get("active_player")
        ]
        if not active_users:
            await ctx.send("No active players to reward.")
            return
        if not self._consume_revenant_use(user):
            await ctx.send("No mythic uses remaining.")
            return
        for name in active_users:
            raffle_cog.state.add_entries(name, 1)
        self._log_event(
            f"Edict: @{username} granted +1 entry to {len(active_users)} active players."
        )
        await ctx.send(
            f"Edict generosity: +1 entry to {len(active_users)} active players."
        )
        usage["edict"] = True
        self.state.save_state()
        self._broadcast_state()
    
    @commands.command(name="greed")
    async def greed(self, ctx):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        if not user.get("is_revenant"):
            await ctx.send("You cannot use that command.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        usage = user.setdefault("stream_usage", {})
        if usage.get("greed"):
            await ctx.send("Greed already used this stream.")
            return
        raffle_cog = self._get_raffle_cog()
        if not raffle_cog:
            await ctx.send("Greed unavailable right now.")
            return
        active_users = [
            name for name, data in self.state.state.get("users", {}).items()
            if data.get("active_player")
        ]
        if not active_users:
            await ctx.send("No active players to harvest from.")
            return
        if not self._consume_revenant_use(user):
            await ctx.send("No mythic uses remaining.")
            return
        gain = len(active_users)
        raffle_cog.state.add_entries(username, gain)
        self._log_event(
            f"Greed: @{username} gained {gain} entries from {len(active_users)} active players."
        )
        await ctx.send(
            f"Greed: @{username} gained {gain} entries from {len(active_users)} active players."
        )
        usage["greed"] = True
        self.state.save_state()
        self._broadcast_state()
    
    @commands.command(name="spawn")
    @mod_only
    async def spawn(self, ctx, *args):
        await self._auto_media_for_command(ctx, "spawn")
        username = ctx.author.name.lower()
        self.logger.info("[RPG] spawn command invoked by %s args=%s", username, args)
        state_obj = self._state_obj()
        if state_obj is None:
            await ctx.send("RPG state unavailable; try !reloadrpg.")
            return
        # Ensure battle loop task exists
        task = getattr(self, "_battle_loop_task", None)
        if task is None or task.done():
            self._battle_loop_task = self.bot.loop.create_task(self._battle_loop())
        # Hard-reset any prior battle state before spawning anew
        try:
            state_obj._reset_battle_on_startup()
        except Exception:
            self.logger.warning("[RPG] spawn: failed to reset battle state", exc_info=True)
        parts = [str(arg).strip() for arg in args if str(arg).strip()]
        if len(parts) < 3:
            self.logger.info("[RPG] spawn failed: insufficient args parts=%s", parts)
            await ctx.send("Usage: !spawn <monster> <level> <count> [slow]")
            return
    
        slow_mode = False
        if parts and parts[-1].lower() == "slow":
            slow_mode = True
            parts = parts[:-1]
    
        if len(parts) < 3:
            self.logger.info("[RPG] spawn failed: insufficient args after slow parts=%s", parts)
            await ctx.send("Usage: !spawn <monster> <level> <count> [slow]")
            return
    
        level_token = parts[-2]
        count_token = parts[-1]
        monster_name = " ".join(parts[:-2]).strip()
    
        if not monster_name:
            self.logger.info("[RPG] spawn failed: empty monster name parts=%s", parts)
            await ctx.send("Usage: !spawn <monster> <level> <count> [slow]")
            return
    
        try:
            level = int(level_token)
            count = int(count_token)
        except Exception:
            self.logger.info("[RPG] spawn failed: bad int level=%s count=%s", level_token, count_token)
            await ctx.send("Usage: !spawn <monster> <level> <count> [slow]")
            return
        if level < 1 or count < 1:
            self.logger.info("[RPG] spawn failed: nonpositive level=%s count=%s", level, count)
            await ctx.send("Level and count must be positive.")
            return
    
        if monster_name.lower() == "pack":
            self.logger.info("[RPG] spawn pack level=%s count=%s slow=%s", level, count, slow_mode)
            try:
                await self._spawn_pack(ctx, level, count, slow_mode=slow_mode, state_obj=state_obj)
            except Exception:
                self.logger.error("[RPG] spawn pack failed", exc_info=True)
                await ctx.send("Spawn pack failed; see logs.")
            return
    
        monster_key = monster_name.lower()
        normalized_key = "".join(ch for ch in monster_key if ch.isalnum())
        loot_goblin_aliases = {
            "loot",
            "lootgoblin",
            "lootgoblins",
            "goblinloot",
            "goblinloots",
        }
        is_explicit_loot_goblin = normalized_key in loot_goblin_aliases
    
        if monster_key == SQUIRREL_NAME:
            level = SQUIRREL_LEVEL
        session = self.state.session()
        self._clear_alchemist_brew_bonuses()
        battle_id = f"battle_{_now_ts()}"
        self.logger.info(
            "[RPG] spawn start battle_id=%s monster=%s level=%s count=%s slow=%s explicit_loot=%s",
            battle_id,
            monster_key,
            level,
            count,
            slow_mode,
            is_explicit_loot_goblin,
        )
        session["battle_active"] = True
        session["battle_id"] = battle_id
        session["channel"] = getattr(ctx.channel, "name", None)
        session["monsters"] = []
        session["turn_number"] = 1
        session["phase"] = "join"
        session["action_queue"] = []
        session["participants"] = []
        session["totems"] = []
        session["imps"] = []
        session["dragons"] = []
        session["green_arrows"] = []
        session["undead_pets"] = []
        session["streamer_pets"] = []
        session["buff_pets"] = []
        session["spirit_wells"] = []
        session["deputy_donut_rounds_remaining"] = 0
        session["barbarian_shout_rounds_remaining"] = 0
        session["battle_stat_baseline"] = {}
        session["slow_actions"] = bool(slow_mode)
        session["join_window_end"] = _now_ts() + JOIN_WINDOW_FIRST_SECONDS
        session["action_window_end"] = None
        for i in range(count):
            if is_explicit_loot_goblin:
                session["monsters"].append(self._build_loot_goblin_entry(i + 1, level))
            else:
                session["monsters"].append(self._build_monster_entry(monster_key, level, i + 1))
        
        # Add loot goblin with a random chance
        if not is_explicit_loot_goblin and random.random() < LOOT_GOBLIN_SPAWN_CHANCE:
            if random.random() < LOOT_GOBLIN_OVERRIDE_CHANCE:
                total = max(1, len(session.get("monsters", [])))
                session["monsters"] = [
                    self._build_loot_goblin_entry(i + 1, level)
                    for i in range(total)
                ]
                self._log_event("Loot Goblin override: entire wave converted!", battle=True)
                await ctx.send("ðŸ’° JACKPOT! The entire wave turned into Loot Goblins! ðŸ’°")
            else:
                session["monsters"].append(self._build_loot_goblin_entry(len(session["monsters"]) + 1, level))
                self._log_event("A Loot Goblin has appeared!", battle=True)
                await ctx.send("â­ A Loot Goblin has appeared! Kill it for bonus rewards! â­")

        state_obj.log["battle_log"] = []
        state_obj.log["battle_id"] = battle_id
        state_obj.save_state()
        state_obj.save_log()

        log_monster_name = "loot goblin" if is_explicit_loot_goblin else monster_key
        self._log_event(f"Battle start: {count}x {log_monster_name} (level {level}).", battle=True)
        slow_note = " Slow mode ON (1s action delay)." if slow_mode else ""
        if is_explicit_loot_goblin:
            await ctx.send(f"Spawned {count} loot goblin(s) at level {level}.{slow_note}")
        else:
            await ctx.send(f"Spawned {count} {monster_key}(s) at level {level}.{slow_note}")
        await ctx.send(f"Join window open for {JOIN_WINDOW_FIRST_SECONDS} seconds. Use !join to fight!")

        try:
            asyncio.create_task(self._ensure_action_window_open(battle_id, session.get("join_window_end")))
        except Exception:
            self.logger.warning("[RPG] failed to schedule action window fallback", exc_info=True)
        # Force-broadcast overlay twice, synchronously, so the clients see the new battle
        try:
            payload = self._build_overlay_payload()
            if payload:
                await broadcast_overlay_message(payload)
            else:
                self.logger.warning("[RPG] spawn sync broadcast skipped: empty payload")
            self.logger.info(
                "[RPG] spawn sync broadcast battle_active=%s phase=%s join_end=%s participants=%s monsters=%s",
                session.get("battle_active"),
                session.get("phase"),
                session.get("join_window_end"),
                len(session.get("participants", [])),
                len(session.get("monsters", [])),
            )
        except Exception:
            self.logger.warning("[RPG] spawn: failed to broadcast state (sync)", exc_info=True)
        self._broadcast_state()
    
    async def _spawn_pack(self, ctx, level: int, count: int, slow_mode: bool = False, state_obj=None):
        state_obj = state_obj or self._state_obj()
        if state_obj is None:
            await ctx.send("RPG state unavailable; try !reloadrpg.")
            return
        try:
            state_obj._reset_battle_on_startup()
        except Exception:
            self.logger.warning("[RPG] spawn pack: failed to reset battle state", exc_info=True)
        session = state_obj.session()
        self._clear_alchemist_brew_bonuses()
        battle_id = f"battle_{_now_ts()}"
        session["battle_active"] = True
        session["battle_id"] = battle_id
        session["channel"] = getattr(ctx.channel, "name", None)
        session["monsters"] = []
        session["turn_number"] = 1
        session["phase"] = "join"
        session["action_queue"] = []
        session["participants"] = []
        session["totems"] = []
        session["imps"] = []
        session["dragons"] = []
        session["green_arrows"] = []
        session["undead_pets"] = []
        session["streamer_pets"] = []
        session["buff_pets"] = []
        session["spirit_wells"] = []
        session["deputy_donut_rounds_remaining"] = 0
        session["barbarian_shout_rounds_remaining"] = 0
        session["battle_stat_baseline"] = {}
        session["slow_actions"] = bool(slow_mode)
        session["join_window_end"] = _now_ts() + JOIN_WINDOW_FIRST_SECONDS
        session["action_window_end"] = None
    
        squirrel_count = 0
        non_squirrel = [name for name in BESTIARY if name != SQUIRREL_NAME]
        for i in range(count):
            choices = BESTIARY
            if squirrel_count >= SQUIRREL_MAX_PACK:
                choices = non_squirrel
            if not choices:
                break
            monster_name = random.choice(choices)
            if monster_name == SQUIRREL_NAME:
                squirrel_count += 1
            session["monsters"].append(self._build_monster_entry(monster_name, level, i + 1))
    
        # Add loot goblin with a random chance
        if random.random() < LOOT_GOBLIN_SPAWN_CHANCE:
            if random.random() < LOOT_GOBLIN_OVERRIDE_CHANCE:
                total = max(1, len(session.get("monsters", [])))
                session["monsters"] = [
                    self._build_loot_goblin_entry(i + 1, level)
                    for i in range(total)
                ]
                self._log_event("Loot Goblin override: entire wave converted!", battle=True)
                await ctx.send("ðŸ’° JACKPOT! The entire wave turned into Loot Goblins! ðŸ’°")
            else:
                session["monsters"].append(self._build_loot_goblin_entry(len(session["monsters"]) + 1, level))
                self._log_event("A Loot Goblin has appeared!", battle=True)
                await ctx.send("â­ A Loot Goblin has appeared! Kill it for bonus rewards! â­")
            self.logger.info(
                "[RPG] spawn session summary monsters=%s phase=%s battle_active=%s join_end=%s",
                len(session.get("monsters", [])),
                session.get("phase"),
                session.get("battle_active"),
                session.get("join_window_end"),
            )
        state_obj.log["battle_log"] = []
        state_obj.log["battle_id"] = battle_id
        state_obj.save_state()
        state_obj.save_log()
    
        counts = {}
        for monster in session.get("monsters", []):
            name = monster.get("name")
            if name == "Loot Goblin":
                continue
            counts[name] = counts.get(name, 0) + 1
        summary = ", ".join(f"{name} x{qty}" for name, qty in counts.items())
        self._log_event(f"Battle start: pack ({summary}) level {level}.", battle=True)
        slow_note = " Slow mode ON (1s action delay)." if slow_mode else ""
        await ctx.send(f"Spawned pack: {summary} (level {level}).{slow_note}")
        await ctx.send(f"Join window open for {JOIN_WINDOW_FIRST_SECONDS} seconds. Use !join to fight!")
        try:
            payload = self._build_overlay_payload()
            if payload:
                await broadcast_overlay_message(payload)
            else:
                self.logger.warning("[RPG] spawn pack sync broadcast skipped: empty payload")
            self.logger.info(
                "[RPG] spawn pack sync broadcast battle_active=%s phase=%s join_end=%s participants=%s monsters=%s",
                session.get("battle_active"),
                session.get("phase"),
                session.get("join_window_end"),
                len(session.get("participants", [])),
                len(session.get("monsters", [])),
            )
        except Exception:
            self.logger.warning("[RPG] spawn pack: failed to broadcast state (sync)", exc_info=True)
        self._broadcast_state()
    
    @commands.command(name="rpgreset")
    @mod_only
    async def rpgreset(self, ctx):
        self._reset_stream_state()
        await ctx.send("RPG stream state reset.")

    @commands.command(name="clearbattle")
    @mod_only
    async def clearbattle(self, ctx):
        state_obj = self._state_obj()
        if state_obj is None:
            await ctx.send("RPG state unavailable; try !reloadrpg.")
            return
        try:
            state_obj._reset_battle_on_startup()
            state_obj.save_state()
            state_obj.save_log()
        except Exception:
            self.logger.warning("[RPG] clearbattle failed", exc_info=True)
            await ctx.send("Failed to clear battle; check logs.")
            return
        self._broadcast_state()
        await ctx.send("Battle state cleared. Waiting for a new battle.")
    
    @commands.command(name="resetcog")
    @mod_only
    async def resetcog(self, ctx):
        self._reset_stream_state()
        await ctx.send("RPG stream state reset.")
    
    @commands.command(name="resetrpg")
    @mod_only
    async def resetrpg(self, ctx):
        try:
            import sys
            # First, remove the cog if it exists
            if self.bot.get_cog("RpgCog"):
                try:
                    self.bot.remove_cog("RpgCog")
                except Exception:
                    pass
            # Clear the module from sys.modules to force a fresh reload
            if "bot.commands.rpg_cog" in sys.modules:
                del sys.modules["bot.commands.rpg_cog"]
            # Now import and prepare fresh
            module = importlib.import_module("bot.commands.rpg_cog")
            if module.prepare:
                module.prepare(self.bot)
            await ctx.send("RPG cog reloaded.")
        except Exception as e:
            await ctx.send(f"Failed to reload RPG cog: {e}")
    
    @commands.command(name="refreshrpg")
    @mod_only
    async def refreshrpg(self, ctx):
        self._reset_stream_state()
        await ctx.send("RPG stream state reset.")

    @commands.command(name="newstream")
    @mod_only
    async def newstream(self, ctx):
        try:
            state_obj = self._state_obj()
            if state_obj is None:
                await ctx.send("RPG state unavailable; try !reloadrpg.")
                return

            self._rollover_stream_only()
            # Ensure active-player flags are reset for all users except streamer
            users = state_obj.state.get("users", {})
            for username, user_data in users.items():
                if username == STREAMER_NAME.lower():
                    user_data["active_player"] = True
                else:
                    user_data["active_player"] = False
                    user_data["daily_embark_ts"] = None
            state_obj.save_state()
            self._broadcast_state()
            await ctx.send("New stream started: active player and salary state reset (battle state unchanged).")
            try:
                self.logger.info("[RPG] newstream: flags reset for %d users", len(users))
            except Exception:
                pass
        except Exception as exc:
            self.logger.exception("[RPG] newstream failed", exc_info=exc)
            await ctx.send(f"newstream failed: {type(exc).__name__}: {exc}")
    
    @commands.command(name="resetdailies")
    @mod_only
    async def resetdailies(self, ctx):
        now_ts = _now_ts()
        self.state.log["daily_reset_ts"] = now_ts
        self.state.log["daily_log"] = []
        self.state.log["battle_log"] = []
        self.state.log["battle_id"] = None
        self._start_new_stream_session()
        
        # Reset per-stream cooldowns and daily timestamps for all users
        reset_count = 0
        reset_users = []
        for username, user_data in self.state.state.get("users", {}).items():
            had_usage = bool(user_data.get("stream_usage"))
            if had_usage:
                reset_count += 1
                reset_users.append(username)
    
            user_data["stream_usage"] = {}
            user_data["daily_embark_ts"] = None
            user_data["salary_claimed_this_stream"] = False
            user_data["salary_claimed_stream_id"] = None
            user_data["revenant_doom_cooldown"] = 0
            user_data["barbarian_whirlwind_cooldown"] = 0
    
            if username == STREAMER_NAME.lower():
                user_data["active_player"] = True
            else:
                user_data["active_player"] = False
    
            if had_usage:
                self._log_event(f"Stream cooldown reset for @{username}.")
        
        self.state.save_state()
        self.state.save_log()
        self._log_event("Daily RPG log reset by mod. Per-stream cooldowns cleared.")
        
        if reset_count > 0:
            await ctx.send(f"RPG daily log reset. Cleared cooldowns for {reset_count} users.")
        else:
            await ctx.send("RPG daily log reset. No cooldowns to clear.")
        
        self._broadcast_state()
    
    @commands.command(name="classchange")
    async def classchange(self, ctx, class_name: str = None):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        if not class_name:
            await ctx.send("Usage: !classchange warrior | rogue | mage | healer")
            return
        if int(user.get("class_tier", 0)) != 1:
            await ctx.send("Class change is only available for base classes right now.")
            return
        tokens = int(user.get("class_change_tokens", 0))
        if tokens <= 0:
            await ctx.send("You have no class change tokens.")
            return
        class_name = class_name.strip().capitalize()
        if class_name not in BASE_CLASSES:
            await ctx.send("Usage: !classchange warrior | rogue | mage | healer")
            return
        user["class_change_tokens"] = tokens - 1
        user["class_name"] = class_name
        user["base_class"] = class_name
        self.state.save_state()
        self._log_event(f"Class change: @{username} became {class_name}.")
        await ctx.send(f"@{username} changed class to {class_name}.")
    
    @commands.command(name="stats")
    async def stats(self, ctx):
        await self._auto_media_for_command(ctx, "stats")
        def _safe_int(value, default=0):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
    
        username = ctx.author.name.lower()
        self.logger.info("[RPG] stats invoked user=%s", username)
        try:
            state_obj = self._state_obj()
            if state_obj is None:
                await ctx.send("RPG state unavailable; try !reloadrpg.")
                return
            user = state_obj.get_user(username)
            self.logger.info(
                "[RPG] stats user=%s class=%s active=%s revenant=%s", 
                username,
                user.get("class_name"),
                bool(user.get("active_player")),
                bool(user.get("is_revenant")),
            )
            class_name = user.get("class_name", "Derp Clone")
            entries = [f"Class: {class_name}", f"HP:{_safe_int(user.get('hp_max', DEFAULT_PLAYER_HP), DEFAULT_PLAYER_HP)}"]
    
            is_ascended = _safe_int(user.get("class_tier", 0), 0) > 0
    
            deaths = _safe_int(user.get("times_knocked_out", 0), 0)
            kills = _safe_int(user.get("killing_blows", 0), 0)
            kdr = f"{kills / deaths:.2f}" if deaths > 0 else (str(kills) if kills > 0 else "0")
    
            if not is_ascended:
                stats = {
                    "Damage": _safe_int(user.get("damage_done", 0), 0),
                    "Healing": _safe_int(user.get("healing_done", 0), 0),
                    "Monsters killed": _safe_int(user.get("monsters_killed", 0), 0),
                    "Killing blows": kills,
                    "Deaths": deaths,
                    "KDR": kdr,
                }
                for label, value in stats.items():
                    if value > 0 or (label in ("Deaths", "KDR") and value != "0"):
                        entries.append(f"{label}: {value}")
    
                if class_name not in ("Monk", "Derp Clone", None) and class_name in BASE_CLASSES:
                    total_xp = _safe_int(user.get("xp", 0), 0)
                    level = self._get_level_from_xp(total_xp, user)
                    xp_at_level, xp_needed = self._get_xp_at_level(total_xp, level, user)
                    level_cap = self._get_level_cap(user)
    
                    if level < level_cap:
                        entries.append(f"Level: {level}/{level_cap} | XP: {xp_at_level}/{xp_needed} (skills +{level-1} effectiveness)")
                    else:
                        entries.append(f"Level: {level}/{level_cap} (maxed - skills +{level-1} effectiveness)")
    
                is_derp_clone = class_name == "Derp Clone" or (class_name is None and user.get("active_player"))
                if is_derp_clone:
                    damage = _safe_int(user.get("damage_done", 0), 0)
                    entries.append(f"Ascend progress: {damage}/{DERP_CLONE_ASCEND_THRESHOLD} damage")
            else:
                total_xp = _safe_int(user.get("xp", 0), 0)
                level = self._get_level_from_xp(total_xp, user)
                xp_at_level, xp_needed = self._get_xp_at_level(total_xp, level, user)
                level_cap = self._get_level_cap(user)
    
                if level < level_cap:
                    entries.append(f"Level: {level}/{level_cap} | XP: {xp_at_level}/{xp_needed} (skills +{level-1} effectiveness)")
                else:
                    entries.append(f"Level: {level}/{level_cap} (maxed - skills +{level-1} effectiveness)")
    
                entries.append(f"Killing blows: {kills}")
                entries.append(f"Deaths: {deaths}")
                entries.append(f"KDR: {kdr}")
    
            if not entries:
                await ctx.send(f"@{username} has no RPG stats yet.")
                return
            await ctx.send(f"@{username} RPG stats | " + " | ".join(entries))
        except Exception:
            self.logger.exception("Stats command failed for @%s", username)
            await ctx.send(f"@{username} stats are temporarily unavailable.")
    
    @commands.command(name="gacha")
    async def gacha(self, ctx, action: str = None, amount: str = None):
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        tokens = int(user.get("class_change_tokens", 0))
        
        if action is None or action.lower() != "draw":
            # Show token count
            await ctx.send(f"@{username} has {tokens} gacha tokens.")
            return
    
        draw_count = 1
        if amount is not None:
            raw_amount = str(amount).strip().lower()
            if raw_amount == "all":
                draw_count = tokens
            else:
                try:
                    draw_count = int(raw_amount)
                except ValueError:
                    await ctx.send("Usage: !gacha | !gacha draw | !gacha draw <positive number|all>")
                    return
                if draw_count <= 0:
                    await ctx.send("Draw amount must be a positive integer.")
                    return
    
        if draw_count <= 0:
            await ctx.send(f"@{username} has no gacha tokens to draw.")
            return
    
        if tokens < draw_count:
            await ctx.send(f"@{username} needs {draw_count} gacha token(s) to draw (you have {tokens}).")
            return
    
        rare_draws = 0
        common_draws = 0
        xp_gained = 0
        bonus_tokens_earned = 0
        bonus_entries_earned = 0
    
        for _ in range(draw_count):
            roll = random.random()
            if roll < GACHA_RARE_CHANCE:
                xp_gained += GACHA_RARE_XP
                rare_draws += 1
            else:
                xp_gained += GACHA_COMMON_XP
                common_draws += 1
    
            if random.random() < GACHA_BONUS_TOKEN_PROC_CHANCE:
                token_roll = random.random()
                cumulative = 0.0
                awarded = 1
                for token_amount, chance in GACHA_BONUS_TOKEN_DISTRIBUTION:
                    cumulative += chance
                    if token_roll <= cumulative:
                        awarded = token_amount
                        break
                bonus_tokens_earned += awarded
    
            if random.random() < GACHA_ENTRY_BONUS_CHANCE:
                bonus_entries_earned += 1
    
        user["class_change_tokens"] = tokens - draw_count + bonus_tokens_earned
        user["xp"] = int(user.get("xp", 0)) + xp_gained
    
        if bonus_entries_earned > 0:
            raffle_cog = self._get_raffle_cog()
            if raffle_cog:
                raffle_cog.state.add_entries(username, bonus_entries_earned)
    
        if self._is_user_revenant(user):
            self.state.session()["revenant_class_xp"] = int(user.get("xp", 0))
        await self._check_for_levelup(username, user)
        
        self.state.save_state()
        self._log_event(
            f"Gacha draw: @{username} drew {draw_count}x for +{xp_gained} XP "
            f"({rare_draws} rare, {common_draws} common)"
            f" | bonus: +{bonus_tokens_earned} gacha, +{bonus_entries_earned} entries."
        )
        self._broadcast_state()
    
        if draw_count == 1:
            rarity = "RARE" if rare_draws == 1 else "COMMON"
            bonus_parts = []
            if bonus_tokens_earned > 0:
                bonus_parts.append(f"+{bonus_tokens_earned} bonus gacha")
            if bonus_entries_earned > 0:
                bonus_parts.append(f"+{bonus_entries_earned} bonus entr{'y' if bonus_entries_earned == 1 else 'ies'}")
            bonus_text = f" | {'; '.join(bonus_parts)}" if bonus_parts else ""
            await ctx.send(
                f"@{username} drew [{rarity}] +{xp_gained} XP! "
                f"(remaining tokens: {user['class_change_tokens']}){bonus_text}"
            )
            return
    
        bonus_summary = []
        if bonus_tokens_earned > 0:
            bonus_summary.append(f"+{bonus_tokens_earned} bonus gacha")
        if bonus_entries_earned > 0:
            bonus_summary.append(f"+{bonus_entries_earned} bonus entr{'y' if bonus_entries_earned == 1 else 'ies'}")
        bonus_text = f" Bonus: {', '.join(bonus_summary)}." if bonus_summary else ""
        await ctx.send(
            f"@{username} drew {draw_count} gacha pulls: +{xp_gained} XP total "
            f"({rare_draws} rare, {common_draws} common). "
            f"Tokens left: {user['class_change_tokens']}.{bonus_text}"
        )
    
    @commands.command(name="loottable")
    async def loottable(self, ctx):
        rare_pct = GACHA_RARE_CHANCE * 100
        common_pct = (1.0 - GACHA_RARE_CHANCE) * 100
        bonus_proc_pct = GACHA_BONUS_TOKEN_PROC_CHANCE * 100
        entry_bonus_pct = GACHA_ENTRY_BONUS_CHANCE * 100
    
        weighted_parts = []
        for token_amount, chance in GACHA_BONUS_TOKEN_DISTRIBUTION:
            weighted_parts.append(f"{token_amount}: {chance * 100:.2f}%")
    
        await ctx.send(
            "Gacha loot table | "
            f"RARE: {rare_pct:.2f}% (+{GACHA_RARE_XP} XP) | "
            f"COMMON: {common_pct:.2f}% (+{GACHA_COMMON_XP} XP) | "
            f"Bonus gacha proc: {bonus_proc_pct:.2f}% (awards 1-10) | "
            f"Bonus entry proc: {entry_bonus_pct:.3f}% | "
            f"Bonus gacha split: {'; '.join(weighted_parts)}"
        )
    
    # ===== STREAMER CLASS COMMANDS (iAmDar only) =====
    
    @commands.command(name="totem")
    async def totem(self, ctx, *, totem_choice: str = None):
        """Streamer skill: Summon a totem with random buff effect."""
        self.logger.info("[RPG] totem invoked by %s choice=%s", ctx.author.name.lower(), totem_choice)
        username = ctx.author.name.lower()
        await self._play_media_fallback("totem", ctx)
        user = self.state.get_user(username)
        if self._is_user_revenant(user):
            self.logger.info("[RPG] totem blocked for %s: revenant", username)
            await ctx.send("Revenants cannot use Streamer skills.")
            return
        if username != STREAMER_NAME.lower() and str(user.get("class_name", "")).strip().lower() != "streamer":
            self.logger.info("[RPG] totem blocked for %s: class mismatch (%s)", username, user.get("class_name"))
            await ctx.send("Only the Streamer can use totem.")
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            self.logger.info("[RPG] totem blocked for %s: knocked out", username)
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            self.logger.info("[RPG] totem blocked for %s: not active", username)
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            self.logger.info("[RPG] totem blocked for %s: no battle", username)
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            self.logger.info("[RPG] totem blocked for %s: phase=%s", username, session.get("phase"))
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            self.logger.info("[RPG] totem blocked for %s: not participant", username)
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            self.logger.info("[RPG] totem blocked for %s: already queued", username)
            await ctx.send("You already queued an action this turn.")
            return
        
        # Check totem limit
        totems = session.get("totems", [])
        active_totems = [t for t in totems if t.get("owner") == username and t.get("alive")]
        if len(active_totems) >= STREAMER_TOTEM_MAX_ACTIVE:
            self.logger.info("[RPG] totem blocked for %s: totem cap reached (%s)", username, len(active_totems))
            await ctx.send(f"You already have {STREAMER_TOTEM_MAX_ACTIVE} totems active!")
            return
    
        active_types = {t.get("buff_type") for t in active_totems}
    
        choice_map = {
            "killshot": "killshot",
            "auto killshot": "killshot",
            "autokillshot": "killshot",
            "ks": "killshot",
            "autocrit": "autocrit",
            "auto crit": "autocrit",
            "crit": "autocrit",
            "shield": "shield",
            "healing": "healing",
            "heal": "healing",
            "party regen": "healing",
            "regen": "healing",
            "damage 5": "damage_5",
            "+5": "damage_5",
            "+5 dmg": "damage_5",
            "damage_5": "damage_5",
            "damage 1": "damage_1",
            "+1": "damage_1",
            "+1 dmg": "damage_1",
            "damage_1": "damage_1",
            "xp": "xp_buff",
            "xp totem": "xp_buff",
            "xp buff": "xp_buff",
            "xp_bonus": "xp_buff",
        }
        
        # Determine totem buff type
        options = [
            ("killshot", TOTEM_KILLSHOT_CHANCE),
            ("autocrit", TOTEM_CRIT_CHANCE),
            ("shield", TOTEM_SHIELD_CHANCE),
            ("healing", TOTEM_HEALING_CHANCE),
            ("damage_5", TOTEM_DAMAGE_5_CHANCE),
            ("damage_1", TOTEM_DAMAGE_1_CHANCE),
            ("xp_buff", 0.25),  # 25% chance to see XP totem in random pool
        ]
        available = [(t, w) for (t, w) in options if t not in active_types]
        if not available:
            await ctx.send("You already have every totem type active.")
            return
    
        normalized_choice = " ".join(str(totem_choice or "").strip().lower().split())
        chosen_type = choice_map.get(normalized_choice) if normalized_choice else None
    
        if normalized_choice and not chosen_type:
            self.logger.info("[RPG] totem blocked for %s: bad choice=%s", username, normalized_choice)
            await ctx.send(
                "Unknown totem. Try: killshot, autocrit, shield, healing, damage 5, or damage 1."
            )
            return
    
        if chosen_type:
            if chosen_type in active_types:
                self.logger.info("[RPG] totem blocked for %s: choice already active (%s)", username, chosen_type)
                chosen_label = self._get_totem_label({"buff_type": chosen_type, "owner": username})
                await ctx.send(f"You already have a {chosen_label} totem active.")
                return
            buff_type = chosen_type
        else:
            total_weight = sum(w for _, w in available)
            roll = random.random() * total_weight
            buff_type = available[-1][0]
            for option_type, weight in available:
                if roll < weight:
                    buff_type = option_type
                    break
                roll -= weight
        totem_id = f"totem_{username}_{_now_ts()}"
        new_totem = {
            "id": totem_id,
            "owner": username,
            "hp": 1,
            "max_hp": 1,
            "alive": True,
            "buff_type": buff_type,
        }
        if buff_type == "xp_buff":
            new_totem["xp_bonus"] = _pick_xp_buff()
        session.setdefault("totems", []).append(new_totem)
        buff_desc = self._get_totem_label(new_totem)
        if buff_type == "xp_buff":
            buff_desc += f" (+{new_totem['xp_bonus']}% XP)"
        
        # Queue totem action
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "totem",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self.logger.info(
            "[RPG] totem queued user=%s buff=%s phase=%s turn=%s queue_len=%s",
            username,
            buff_type,
            session.get("phase"),
            session.get("turn_number"),
            len(session.get("action_queue", [])),
        )
        self._log_event(f"Queued: @{username} summoned totem ({buff_desc}).", battle=True)
        await ctx.send(f"@{username} summoned a totem with {buff_desc}!")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="rez")
    async def rez(self, ctx, target: str = None):
        """Streamer skill: Resurrect a knocked out party member to half health."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("rez", ctx)
        user = self.state.get_user(username)
        if username != STREAMER_NAME.lower() or self._is_user_revenant(user):
            return
        
        if not target:
            await ctx.send("Usage: !rez @username or !rez <party number>")
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        # Parse target by party number (1-indexed) or username
        raw_target = str(target).strip()
        target_name = None
        numeric_target = raw_target.lstrip("#")
        if numeric_target.isdigit():
            party_index = int(numeric_target) - 1
            if party_index < 0 or party_index >= len(participants):
                await ctx.send(f"Invalid party member. Use a number 1-{len(participants)}.")
                return
            target_name = participants[party_index]
        else:
            target_name = raw_target.lower().lstrip("@")
    
        if target_name not in participants:
            await ctx.send(f"@{target_name} is not in this battle.")
            return
        
        # Cannot rez totems or imps (they're not in participants list anyway, but for clarity)
        if "totem" in target_name.lower() or "imp" in target_name.lower():
            await ctx.send("Cannot resurrect totems or imps.")
            return
        
        target_user = self.state.get_user(target_name)
        target_hp = int(target_user.get("hp_current", DEFAULT_PLAYER_HP))
        
        if target_hp > 0:
            await ctx.send(f"@{target_name} is already alive.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Queue rez action with target
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "rez",
            "damage": 0,
            "target_index": None,
            "rez_target": target_name,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self._log_event(f"Queued: @{username} rez'd @{target_name}.", battle=True)
        await ctx.send(f"@{username} will resurrect @{target_name}!")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="gamba")
    async def gamba(self, ctx):
        """Streamer skill: Chance-based AoE that can occasionally backfire on the streamer."""
        self.logger.info("[RPG] gamba invoked by %s", ctx.author.name.lower())
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("gamba", ctx)
        if self._is_user_revenant(user):
            await ctx.send("Revenants cannot use Streamer skills.")
            return

        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "streamer" and username != STREAMER_NAME.lower():
            await ctx.send("Only the Streamer can use gamba.")
            return

        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return

        session = self.state.session()

        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return

        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return

        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
    
        action_queue = session.get("action_queue", [])
        existing_entry = next((entry for entry in action_queue if entry.get("user") == username), None)
    
        if existing_entry:
            previous_action = str(existing_entry.get("action", "action"))
            existing_entry["action"] = "gamba"
            existing_entry["damage"] = 0
            existing_entry["target_index"] = None
            existing_entry["ts"] = _now_ts()
            action_msg = f"@{username} switched from {previous_action} to gamba! Will it pop off... or backfire?"
            log_msg = f"Queued: @{username} switched from {previous_action} to gamba."
        else:
            session.setdefault("action_queue", []).append({
                "user": username,
                "action": "gamba",
                "damage": 0,
                "target_index": None,
                "ts": _now_ts(),
            })
            action_msg = f"@{username} rolled gamba! Will it pop off... or backfire?"
            log_msg = f"Queued: @{username} rolled gamba."
    
        self.state.save_state()
        self._log_event(log_msg, battle=True)
        await ctx.send(action_msg)
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    # ===== WARLOCK CLASS COMMANDS (fal_the_warlock only) =====
    
    @commands.command(name="corruption")
    async def corruption(self, ctx, target_index: str = None):
        """Warlock skill: Apply a DoT that damages target for 3 turns (scales with level)."""
        self.logger.info("[RPG] corruption invoked by %s target=%s", ctx.author.name.lower(), target_index)
        username = ctx.author.name.lower()
        await self._play_media_fallback("corruption", ctx)
        user = self.state.get_user(username)
        session = self.state.session()
    
        if username != WARLOCK_NAME.lower() or self._is_user_revenant(user):
            return
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Parse target
        if target_index is not None:
            cleaned = "".join(ch for ch in str(target_index) if ch.isdigit())
            if cleaned == "":
                target_index = None
            else:
                try:
                    target_index = int(cleaned)
                except Exception:
                    await ctx.send("Target must be a monster number like !corruption 1.")
                    return
        
        if target_index is not None:
            if not self._get_monster_by_index(session, target_index):
                await ctx.send("That monster number is not available.")
                return
        
        # Queue corruption action
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "corruption",
            "damage": 0,
            "target_index": target_index,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        target_note = f" on monster {target_index}" if target_index else ""
        self._log_event(f"Queued: @{username} corruption{target_note}.", battle=True)
        await ctx.send(f"@{username} queued corruption{target_note}!")
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="doom")
    async def doom(self, ctx):
        """Revenant ultimate: hit all afflicted enemies and apply berzerk."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("doom", ctx)
        user = self.state.get_user(username)
        session = self.state.session()
    
        if not user.get("is_revenant"):
            return
        if int(user.get("revenant_doom_cooldown", 0)) > 0:
            await ctx.send(
                f"Doom cooldown: {int(user.get('revenant_doom_cooldown', 0))} turns remaining."
            )
            return
    
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "revenant_doom",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self._log_event(f"Queued: @{username} doom.", battle=True)
        await ctx.send(f"@{username} queued DOOM on all afflicted enemies!")
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="sb")
    async def shadowbolt(self, ctx, target_index: str = None):
        """Warlock skill: Direct damage similar to bolt."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("sb", ctx)
        user = self.state.get_user(username)
        if username != WARLOCK_NAME.lower() or self._is_user_revenant(user):
            return
        session = self.state.session()
    
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
    
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        # Parse target
        if target_index is not None:
            cleaned = "".join(ch for ch in str(target_index) if ch.isdigit())
            if cleaned == "":
                target_index = None
            else:
                try:
                    target_index = int(cleaned)
                except Exception:
                    await ctx.send("Target must be a monster number like !sb 1.")
                    return
    
        if target_index is not None:
            if not self._get_monster_by_index(session, target_index):
                await ctx.send("That monster number is not available.")
                return
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "shadowbolt",
            "damage": SHADOWBOLT_BASE_DAMAGE,
            "target_index": target_index,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        target_note = f" on monster {target_index}" if target_index else ""
        self._log_event(f"Queued: @{username} shadowbolt{target_note}.", battle=True)
        await ctx.send(f"@{username} queued shadowbolt{target_note}!")
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="summon_imp")
    async def summon_imp(self, ctx):
        """Warlock skill: Summon an imp that fireballs for damage equal to warlock level."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("summon_imp", ctx)
        user = self.state.get_user(username)
        if username != WARLOCK_NAME.lower() or self._is_user_revenant(user):
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Check if imp already exists
        imps = session.get("imps", [])
        if any(imp.get("owner") == username and imp.get("alive") for imp in imps):
            await ctx.send("You already have an imp summoned!")
            return
        dragons = session.get("dragons", [])
        if any(dragon.get("owner") == username and dragon.get("alive") for dragon in dragons):
            await ctx.send("You already have a dragon summoned!")
            return
        
        # Create imp
        imp_id = f"imp_{username}_{_now_ts()}"
        warlock_level = self._get_level_from_xp(int(user.get("xp", 0)), user)
        session.setdefault("imps", []).append({
            "id": imp_id,
            "owner": username,
            "alive": True,
            "damage": warlock_level,
        })
        
        # Queue summon action
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "summon_imp",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self._log_event(f"Queued: @{username} summoned imp ({warlock_level} dmg).", battle=True)
        await ctx.send(f"@{username} summoned an imp that will fireball for {warlock_level} damage!")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="dragon")
    async def summon_dragon(self, ctx):
        """Warlock skill: Summon a dragon that bites, applies dragonfire DoT, and rarely uses CLAW."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("dragon", ctx)
        user = self.state.get_user(username)
        if username != WARLOCK_NAME.lower() or self._is_user_revenant(user):
            return
    
        session = self.state.session()
    
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
    
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        imps = session.get("imps", [])
        if any(imp.get("owner") == username and imp.get("alive") for imp in imps):
            await ctx.send("You already have an imp summoned!")
            return
    
        dragons = session.get("dragons", [])
        if any(dragon.get("owner") == username and dragon.get("alive") for dragon in dragons):
            await ctx.send("You already have a dragon summoned!")
            return
    
        warlock_level = self._get_level_from_xp(int(user.get("xp", 0)), user)
        dragon_hp = DRAGON_BASE_HP + (warlock_level - 1) * DRAGON_HP_PER_LEVEL
        dragon_attack_damage, dragon_dot_damage, dragon_claw_damage = self._get_dragon_combat_stats(username)
        dragon_id = f"dragon_{username}_{_now_ts()}"
        session.setdefault("dragons", []).append({
            "id": dragon_id,
            "owner": username,
            "alive": True,
            "hp": dragon_hp,
            "max_hp": dragon_hp,
            "damage": dragon_dot_damage,
            "attack_damage": dragon_attack_damage,
            "claw_damage": dragon_claw_damage,
            "claw_chance": DRAGON_CLAW_CHANCE,
        })
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "summon_dragon",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self._log_event(
            f"Queued: @{username} summoned a dragon ({dragon_hp} HP, {dragon_attack_damage} bite, {dragon_dot_damage} dragonfire DoT).",
            battle=True,
        )
        await ctx.send(
            f"@{username} summoned a dragon ({dragon_hp} HP)! It can bite, apply dragonfire, and rarely use CLAW."
        )
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    # ===== HOP CLASS COMMANDS (hoplon5 only) =====
    
    @commands.command(name="sap")
    async def sap(self, ctx, target_index: str = None):
        """Hop skill: Has a chance to stun the target."""
        username = ctx.author.name.lower()
        self.logger.info("[RPG] sap invoked by %s target=%s", username, target_index)
        await self._play_media_fallback("sap", ctx)
        if username != HOP_NAME.lower() or self._is_user_revenant(self.state.get_user(username)):
            return
        await self._queue_monster_action(
            ctx,
            "sap",
            0,
            required_class="Hop",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="deagle")
    async def deagle(self, ctx, target_index: str = None):
        """Hop skill: Attack with chance for heavy damage (2x)."""
        username = ctx.author.name.lower()
        self.logger.info("[RPG] deagle invoked by %s target=%s", username, target_index)
        await self._play_media_fallback("deagle", ctx)
        if username != HOP_NAME.lower() or self._is_user_revenant(self.state.get_user(username)):
            return
        await self._queue_monster_action(
            ctx,
            "deagle",
            HOP_DEAGLE_BASE_DAMAGE,
            required_class="Hop",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="c4")
    async def c4(self, ctx):
        """Hop skill: Throw C4 that has a chance to damage all enemies."""
        username = ctx.author.name.lower()
        self.logger.info("[RPG] c4 invoked by %s", username)
        await self._play_media_fallback("c4", ctx)
        user = self.state.get_user(username)
        if username != HOP_NAME.lower() or self._is_user_revenant(user):
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Queue c4 action (no specific target, hits all)
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "c4",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self._log_event(f"Queued: @{username} threw C4.", battle=True)
        await ctx.send(f"@{username} prepared C4!")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="goldrpg")
    async def goldrpg(self, ctx, target_index: str = None):
        """Hop skill: Crit-gated golden rocket attack with splash and global bleed."""
        username = ctx.author.name.lower()
        self.logger.info("[RPG] goldrpg invoked by %s target=%s", username, target_index)
        await self._play_media_fallback("goldrpg", ctx)
        user = self.state.get_user(username)
        if username != HOP_NAME.lower() or self._is_user_revenant(user):
            return
    
        if not user.get("hop_goldrpg_ready"):
            return
    
        await self._queue_monster_action(
            ctx,
            "goldrpg",
            HOP_GOLDRPG_BASE_DAMAGE,
            required_class="Hop",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="greenarrow")
    async def greenarrow(self, ctx):
        """Hop skill: Summon 1-6 Green Arrows that absorb the first monster attack."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("greenarrow", ctx)
        user = self.state.get_user(username)
        if username != HOP_NAME.lower() or self._is_user_revenant(user):
            return
    
        session = self.state.session()
    
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            return
    
        if not user.get("active_player"):
            return
        if not session.get("battle_active"):
            return
        if session.get("phase") != "action":
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        session.setdefault("green_arrows", [])
        active_arrows = [
            a for a in session.get("green_arrows", [])
            if a.get("owner") == username and a.get("alive")
        ]
        remaining_slots = HOP_GREENARROW_MAX - len(active_arrows)
        if remaining_slots <= 0:
            await ctx.send("You already have 6 Green Arrows active!")
            return
    
        # Weighted roll for 1-6 arrows
        roll = random.random()
        cumulative = 0.0
        spawn_count = 1
        for index, chance in enumerate(HOP_GREENARROW_CHANCES, start=1):
            cumulative += chance
            if roll <= cumulative:
                spawn_count = index
                break
    
        spawn_count = min(spawn_count, remaining_slots)
        for _ in range(spawn_count):
            arrow_id = f"green_arrow_{username}_{_now_ts()}_{random.randint(1000, 9999)}"
            session["green_arrows"].append({
                "id": arrow_id,
                "owner": username,
                "alive": True,
                "hp": 1,
                "max_hp": 1,
            })
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "greenarrow",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        total_arrows = len([
            a for a in session["green_arrows"]
            if a.get("owner") == username and a.get("alive")
        ])
        self.state.save_state()
        self._log_event(f"Queued: @{username} summoned {spawn_count} Green Arrow(s).", battle=True)
        await ctx.send(f"@{username} summoned {spawn_count} Green Arrow(s)! (Total: {total_arrows}/6)")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    # ===== DEPUTY CLASS COMMANDS =====
    
    @commands.command(name="tazer", aliases=("taze",))
    async def tazer(self, ctx, target_index: str = None):
        """Deputy skill: Shock a target with a strong chance to stun for 1 turn."""
        username = ctx.author.name.lower()
        played = await self._play_media_fallback("tazer", ctx)
        if not played:
            await self._play_media_fallback("taze", ctx)
        if username != DEPUTY_NAME.lower() or self._is_user_revenant(self.state.get_user(username)):
            return
        await self._queue_monster_action(
            ctx,
            "tazer",
            DEPUTY_TAZE_BASE_DAMAGE,
            required_class="Deputy",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="teargass")
    async def teargass(self, ctx):
        """Deputy skill: Area stun with descending per-target probability; 4-turn cooldown."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("teargass", ctx)
        user = self.state.get_user(username)
        if username != DEPUTY_NAME.lower() or self._is_user_revenant(user):
            return
    
        session = self.state.session()
    
        if int(user.get("deputy_teargass_cooldown", 0)) > 0:
            await ctx.send(f"Teargass cooldown: {int(user.get('deputy_teargass_cooldown', 0))} turns remaining.")
            return
    
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            return
        if not user.get("active_player"):
            return
        if not session.get("battle_active"):
            return
        if session.get("phase") != "action":
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "teargass",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self._log_event(f"Queued: @{username} deployed teargass.", battle=True)
        await ctx.send(f"@{username} primed TEARGASS!")
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="tommygun")
    async def tommygun(self, ctx, target_index: str = None):
        """Deputy skill: Multihit burst on one target, scaling per-hit damage with Deputy level; 2-turn cooldown."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("tommygun", ctx)
        user = self.state.get_user(username)
        if username != DEPUTY_NAME.lower() or self._is_user_revenant(user):
            return
    
        if int(user.get("deputy_tommygun_cooldown", 0)) > 0:
            await ctx.send(f"Tommygun cooldown: {int(user.get('deputy_tommygun_cooldown', 0))} turns remaining.")
            return
    
        await self._queue_monster_action(
            ctx,
            "tommygun",
            0,
            required_class="Deputy",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="donut")
    async def donut(self, ctx):
        """Deputy skill: Gives the party +10% effectiveness; 5-turn cooldown."""
        username = ctx.author.name.lower()
        await self._play_media_fallback("donut", ctx)
        user = self.state.get_user(username)
        if username != DEPUTY_NAME.lower() or self._is_user_revenant(user):
            return
    
        session = self.state.session()
    
        if int(user.get("deputy_donut_cooldown", 0)) > 0:
            await ctx.send(f"Donut cooldown: {int(user.get('deputy_donut_cooldown', 0))} turns remaining.")
            return
    
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            return
        if not user.get("active_player"):
            return
        if not session.get("battle_active"):
            return
        if session.get("phase") != "action":
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "donut",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self._log_event(f"Queued: @{username} served donuts.", battle=True)
        await ctx.send(f"@{username} served donuts to the party!")
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    # ===== BUFF CLASS COMMANDS =====
    
    @commands.command(name="kid")
    async def kid(self, ctx):
        self.logger.info("[RPG] kid invoked by %s", ctx.author.name.lower())
        try:
            username = ctx.author.name.lower()
            await self._play_media_fallback("kid", ctx)
            user = self.state.get_user(username)
            session = self.state.session()

            if not await self._can_use_buff_command(ctx, username, user, "kid"):
                return

            if not await self._validate_buff_turn_rule(ctx, "kid", session):
                self.logger.info("[RPG] kid blocked for %s: turn rule", username)
                return

            current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
            if current_hp <= 0:
                self.logger.info("[RPG] kid blocked for %s: knocked out", username)
                await ctx.send("You are knocked out and cannot act.")
                return
            if not user.get("active_player"):
                self.logger.info("[RPG] kid blocked for %s: not active", username)
                await ctx.send("You must join the battle first.")
                return
            if not session.get("battle_active"):
                self.logger.info("[RPG] kid blocked for %s: no battle", username)
                await ctx.send("No active battle.")
                return
            if session.get("phase") != "action":
                self.logger.info("[RPG] kid blocked for %s: phase=%s", username, session.get("phase"))
                await ctx.send("Action window is closed.")
                return

            participants = session.setdefault("participants", [])
            if username not in participants:
                self.logger.info("[RPG] kid blocked for %s: not participant", username)
                await ctx.send("You must !join before acting.")
                return

            action_queue = session.get("action_queue", [])
            if any(entry.get("user") == username for entry in action_queue):
                self.logger.info("[RPG] kid blocked for %s: already queued", username)
                await ctx.send("You already queued an action this turn.")
                return

            existing_kid = any(
                p.get("alive") and str(p.get("owner", "")).lower() == username and str(p.get("pet_type", "")).lower() == "kid"
                for p in session.get("buff_pets", [])
            )
            if existing_kid:
                self.logger.info("[RPG] kid blocked for %s: kid already active", username)
                await ctx.send("Kid is already active.")
                return

            pet_id = f"buff_kid_{username}_{_now_ts()}"
            session.setdefault("buff_pets", []).append({
                "id": pet_id,
                "owner": username,
                "pet_type": "kid",
                "hp": BUFF_KID_BASE_HP,
                "max_hp": BUFF_KID_BASE_HP,
                "alive": True,
                "intercept_chance": BUFF_KID_INTERCEPT_CHANCE,
            })

            session.setdefault("action_queue", []).append({
                "user": username,
                "action": "kid",
                "damage": 0,
                "target_index": None,
                "ts": _now_ts(),
            })

            self.state.save_state()
            self.logger.info(
                "[RPG] kid queued user=%s phase=%s turn=%s queue_len=%s",
                username,
                session.get("phase"),
                session.get("turn_number"),
                len(session.get("action_queue", [])),
            )
            self._log_event(f"Queued: @{username} summoned Kid.", battle=True)
            await ctx.send(f"@{username} summoned Kid (25% chance to intercept and insta-kill a random mob)!" )
            self._broadcast_state()
            await self._resolve_turn_if_ready(session)
        except Exception:
            self.logger.exception("[RPG] kid failed for %s", ctx.author.name.lower(), exc_info=True)
            try:
                await ctx.send("Kid failed: unexpected error.")
            except Exception:
                pass
    
    @commands.command(name="franklin")
    async def franklin(self, ctx):
        self.logger.info("[RPG] franklin invoked by %s", ctx.author.name.lower())
        username = ctx.author.name.lower()
        await self._play_media_fallback("franklin", ctx)
        user = self.state.get_user(username)
        session = self.state.session()
    
        if not await self._can_use_buff_command(ctx, username, user, "franklin"):
            return
    
        if not await self._validate_buff_turn_rule(ctx, "franklin", session):
            self.logger.info("[RPG] franklin blocked for %s: turn rule", username)
            return
    
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            self.logger.info("[RPG] franklin blocked for %s: knocked out", username)
            await ctx.send("You are knocked out and cannot act.")
            return
        if not user.get("active_player"):
            self.logger.info("[RPG] franklin blocked for %s: not active", username)
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            self.logger.info("[RPG] franklin blocked for %s: no battle", username)
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            self.logger.info("[RPG] franklin blocked for %s: phase=%s", username, session.get("phase"))
            await ctx.send("Action window is closed.")
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            self.logger.info("[RPG] franklin blocked for %s: not participant", username)
            await ctx.send("You must !join before acting.")
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            self.logger.info("[RPG] franklin blocked for %s: already queued", username)
            await ctx.send("You already queued an action this turn.")
            return
    
        existing_franklin = any(
            p.get("alive") and str(p.get("owner", "")).lower() == username and str(p.get("pet_type", "")).lower() == "franklin"
            for p in session.get("buff_pets", [])
        )
        if existing_franklin:
            self.logger.info("[RPG] franklin blocked for %s: franklin already active", username)
            await ctx.send("Franklin is already active.")
            return
    
        pet_id = f"buff_franklin_{username}_{_now_ts()}"
        session.setdefault("buff_pets", []).append({
            "id": pet_id,
            "owner": username,
            "pet_type": "franklin",
            "hp": BUFF_FRANKLIN_BASE_HP,
            "max_hp": BUFF_FRANKLIN_BASE_HP,
            "alive": True,
            "damage": BUFF_FRANKLIN_BASE_DAMAGE,
            "crit_chance": BUFF_FRANKLIN_CRIT_CHANCE,
        })
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "franklin",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self.logger.info(
            "[RPG] franklin queued user=%s phase=%s turn=%s queue_len=%s",
            username,
            session.get("phase"),
            session.get("turn_number"),
            len(session.get("action_queue", [])),
        )
        self._log_event(f"Queued: @{username} summoned Franklin.", battle=True)
        await ctx.send(f"@{username} summoned Franklin (high crit chance)!" )
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="jdam")
    async def jdam(self, ctx, target_index: str = None):
        self.logger.info("[RPG] jdam invoked by %s target=%s", ctx.author.name.lower(), target_index)
        username = ctx.author.name.lower()
        await self._play_media_fallback("jdam", ctx)
        user = self.state.get_user(username)
        session = self.state.session()
    
        if not await self._can_use_buff_command(ctx, username, user, "jdam"):
            return
    
        if not await self._validate_buff_turn_rule(ctx, "jdam", session):
            self.logger.info("[RPG] jdam blocked for %s: turn rule", username)
            return
    
        await self._queue_monster_action(
            ctx,
            "jdam",
            BUFF_JDAM_BASE_DAMAGE,
            required_class="Buff",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="nuke")
    async def nuke(self, ctx):
        username = ctx.author.name.lower()
        await self._play_media_fallback("nuclear", ctx)
        user = self.state.get_user(username)
        session = self.state.session()
    
        if not await self._can_use_buff_command(ctx, username, user, "nuke"):
            return
    
        if not await self._validate_buff_turn_rule(ctx, "nuke", session):
            return
    
        if not bool(user.get("buff_kid_intercept_triggered")):
            await ctx.send("Nuke locked: Kid has not intercepted an attack yet.")
            return
        if not bool(user.get("buff_franklin_crit_triggered")):
            await ctx.send("Nuke locked: Franklin has not landed a crit yet.")
            return
        if not bool(user.get("buff_jdam_crit_triggered")):
            await ctx.send("Nuke locked: JDAM has not landed a crit yet.")
            return
    
        await self._queue_monster_action(
            ctx,
            "nuke",
            0,
            required_class="Buff",
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    # ===== KHAJIIT CLASS COMMANDS =====
    
    @commands.command(name="scratch")
    async def scratch(self, ctx, target_index: str = None):
        """Khajiit skill: Moderate damage with chance to apply bleed."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("scratch", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "khajiit" and username != KHAJIIT_NAME.lower():
            return
        await self._queue_monster_action(
            ctx,
            "scratch",
            KHAJIIT_SCRATCH_BASE_DAMAGE,
            required_class="Khajiit",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="hairball")
    async def hairball(self, ctx, target_index: str = None):
        """Khajiit skill: Direct damage with chance to 'gross out' enemies (DoT)."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("hairball", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "khajiit" and username != KHAJIIT_NAME.lower():
            return
        await self._queue_monster_action(
            ctx,
            "hairball",
            KHAJIIT_HAIRBALL_BASE_DAMAGE,
            required_class="Khajiit",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="meow")
    async def meow(self, ctx):
        """Khajiit skill: Knock a random object off the shelf with varying effects."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("meow", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "khajiit" and username != KHAJIIT_NAME.lower():
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Determine which object gets knocked off (weighted random)
        roll = random.random()
        
        # Define item effects and probabilities
        # Light damage: 45% chance
        # Moderate damage: 35% chance
        # Heavy damage: 18% chance
        # Insta-kill single enemy: 1.9% chance
        # "Heavy lourde" (enemy wipe): 0.1% chance
        
        if roll < 0.45:
            # Light damage item
            items = ["stapler", "pen", "coffee mug", "remote control", "phone"]
            item = random.choice(items)
            effect_type = "light"
            damage = KHAJIIT_MEOW_LIGHT_BASE_DAMAGE
        elif roll < 0.80:
            # Moderate damage item
            items = ["laptop", "monitor", "printer", "keyboard", "desk lamp"]
            item = random.choice(items)
            effect_type = "moderate"
            damage = KHAJIIT_MEOW_MODERATE_BASE_DAMAGE
        elif roll < 0.98:
            # Heavy damage item
            items = ["bookshelf", "filing cabinet", "potted plant", "office chair"]
            item = random.choice(items)
            effect_type = "heavy"
            damage = KHAJIIT_MEOW_HEAVY_BASE_DAMAGE
        elif roll < 0.999:
            # Insta-kill single enemy
            item = "bowling ball"
            effect_type = "instakill"
            damage = 0
        else:
            # Enemy wipe (heavy lourde)
            item = "heavy lourde"
            effect_type = "enemy_wipe"
            damage = 0
        
        # Queue meow action with effect data
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "meow",
            "item": item,
            "effect_type": effect_type,
            "damage": damage,
            "target_index": None,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self._log_event(f"Queued: @{username} knocked a {item} off the shelf!", battle=True)
        await ctx.send(f"@{username} knocked a {item} off the shelf!")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    # ===== KHAJIIT STREAM SKILL =====
    
    @commands.command(name="coin")
    async def coin(self, ctx):
        """Khajiit stream skill: Give 1-5 raffle entries to all OTHER active players."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("coin", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "khajiit" and username != KHAJIIT_NAME.lower():
            return
    
        if not user.get("active_player"):
            await ctx.send("You must join the adventure first.")
            return
        
        if user.get("stream_usage", {}).get("coin"):
            await ctx.send("Coin already used this stream.")
            return
        
        # Get all active players except caerdwyn
        users = self.state.state.get("users", {})
        active_others = [
            name for name, data in users.items() 
            if data.get("active_player") and name != username
        ]
        
        if not active_others:
            await ctx.send("No other active players to share coins with!")
            return
        
        # Determine entry count with weighted random: 50%, 30%, 15%, 4%, 1%
        roll = random.random()
        if roll < 0.50:
            entries = 1
        elif roll < 0.80:  # 50% + 30%
            entries = 2
        elif roll < 0.95:  # 80% + 15%
            entries = 3
        elif roll < 0.99:  # 95% + 4%
            entries = 4
        else:
            entries = 5
        
        # Grant entries to all other active players
        raffle_cog = self._get_raffle_cog()
        if raffle_cog:
            for player in active_others:
                raffle_cog.state.add_entries(player, entries)
        
        # Mark as used
        user.setdefault("stream_usage", {})["coin"] = True
        self.state.save_state()
        
        recipients = ", ".join(f"@{name}" for name in active_others)
        self._log_event(f"Coin: @{username} gave {entries} entries to {len(active_others)} players.")
        await ctx.send(f"ðŸª™ @{username} flips coins! Everyone gets {entries} raffle entr{'y' if entries == 1 else 'ies'}! ({recipients})")
        self._broadcast_state()
    
    # ===== ALCHEMIST CLASS COMMANDS =====
    
    @commands.command(name="brew")
    async def brew(self, ctx):
        """Alchemist skill: Randomly buffs at least 3 allies or applies drunk to all enemies."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("brew", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "alchemist" and username != ALCHEMIST_NAME.lower():
            return
    
        session = self.state.session()
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
    
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
    
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
    
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "brew",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
    
        self.state.save_state()
        self._log_event(f"Queued: @{username} mixed a volatile brew.", battle=True)
        await ctx.send(f"ðŸ§ª @{username} mixes a brew!")
        self._broadcast_state()
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="bottle")
    async def bottle(self, ctx, target_index: str = None):
        """Alchemist skill: Decent direct damage with crit/bleed chance and up to 2 bleeding shard hits."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("bottle", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "alchemist" and username != ALCHEMIST_NAME.lower():
            return
        await self._queue_monster_action(
            ctx,
            "bottle",
            ALCHEMIST_BOTTLE_BASE_DAMAGE,
            required_class="Alchemist",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    # ===== ARCHANGEL CLASS COMMANDS =====
    
    @commands.command(name="pray")
    async def pray(self, ctx):
        """Archangel skill: +2 power, +3 self heal."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("pray", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "archangel" and username != ARCHANGEL_NAME.lower():
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Queue pray action
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "pray",
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self._log_event(f"Queued: @{username} prays for divine power.", battle=True)
        await ctx.send(f"ðŸ™ @{username} prays!")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="touch")
    async def touch(self, ctx, target_index: str = None):
        """Archangel skill: +1 power, 3 base damage to monster."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("touch", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "archangel" and username != ARCHANGEL_NAME.lower():
            return
        await self._queue_monster_action(
            ctx,
            "touch",
            ARCHANGEL_TOUCH_BASE_DAMAGE,
            required_class="Archangel",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="expel")
    async def expel(self, ctx):
        """Archangel skill: ((level/10)+(power*2)) AoE damage + (((level/10)*power)+power) party heal, then reduce power by 2."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("expel", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "archangel" and username != ARCHANGEL_NAME.lower():
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        power = int(user.get("archangel_power", 0))
        if power == 0:
            await ctx.send("You need power first! Use !pray or !touch to build power.")
            return
        
        # Queue expel action
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "expel",
            "damage": 0,  # Calculated during resolution
            "target_index": None,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self._log_event(f"Queued: @{username} expels with {power} power.", battle=True)
        await ctx.send(f"âœ¨ @{username} prepares to expel with {power} power!")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    @commands.command(name="judgement")
    async def judgement(self, ctx, target_index: str = None):
        """Archangel skill: (2*(level*power))+(5*power) damage to target, then set power to 0."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("judgement", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "archangel" and username != ARCHANGEL_NAME.lower():
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        power = int(user.get("archangel_power", 0))
        if power == 0:
            await ctx.send("You need power first! Use !pray or !touch to build power.")
            return
        
        # Parse target
        if target_index is not None:
            cleaned = "".join(ch for ch in str(target_index) if ch.isdigit())
            if cleaned == "":
                target_index = None
            else:
                try:
                    target_index = int(cleaned)
                except Exception:
                    await ctx.send("Target must be a monster number like !judgement 1.")
                    return
        
        if target_index is not None:
            if not self._get_monster_by_index(session, target_index):
                await ctx.send("That monster number is not available.")
                return
        
        # Queue judgement action
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "judgement",
            "damage": 0,  # Calculated during resolution
            "target_index": target_index,
            "ts": _now_ts(),
        })
        
        self.state.save_state()
        self._log_event(f"Queued: @{username} judges with {power} power.", battle=True)
        await ctx.send(f"âš–ï¸ @{username} prepares judgement with {power} power!")
        self._broadcast_state()
    
        await self._resolve_turn_if_ready(session)
    
    # ===== MEATWAD CLASS COMMANDS =====
    
    @commands.command(name="gun")
    async def gun(self, ctx, target_index: str = None):
        """Meatwad skill: Basic direct damage attack that scales with level/crit."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._maybe_trigger_media("gun", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "meatwad" and username not in MEATWAD_ALIASES:
            return
        await self._queue_monster_action(
            ctx,
            "gun",
            MEATWAD_GUN_BASE_DAMAGE,
            required_class="Meatwad",
            target_index=target_index,
            allow_media_fallback=False,
            silent_on_class_mismatch=True,
        )
    
    @commands.command(name="transform")
    async def transform(self, ctx):
        """Meatwad skill: Transform into a random form with unique passive effects."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("transform", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "meatwad" and username not in MEATWAD_ALIASES:
            return
    
        session = self.state.session()
        
        # Check if player is knocked out
        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot transform.")
            return
        
        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return
        
        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before transforming.")
            return
        
        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return
        
        # Select random transformation based on weighted probabilities and level gates
        level = self._get_level_from_xp(int(user.get("xp", 0)), user)
        eligible_forms = [t for t in MEATWAD_TRANSFORMATIONS if t[5] <= level]
        if not eligible_forms:
            eligible_forms = [t for t in MEATWAD_TRANSFORMATIONS if t[5] <= 1]
        if not eligible_forms:
            eligible_forms = MEATWAD_TRANSFORMATIONS
    
        total_weight = sum(t[1] for t in eligible_forms)
        roll = random.random() * total_weight
        cumulative = 0
        selected_form = None
    
        for transformation in eligible_forms:
            name, weight, effect_type, effect_value, description, _ = transformation
            cumulative += weight
            if roll <= cumulative:
                selected_form = transformation
                break
        
        # Fallback to first form if something went wrong
        if selected_form is None:
            selected_form = MEATWAD_TRANSFORMATIONS[0]
        
        form_name, _, effect_type, effect_value, description, _ = selected_form
        
        # Save the transformation
        user["meatwad_form"] = {
            "name": form_name,
            "effect_type": effect_type,
            "effect_value": effect_value,
            "description": description,
        }
        
        # Determine rarity label for display
        weight = selected_form[1]
        if weight <= 0.5:
            rarity = "âœ¨ MYTHICAL âœ¨"
        elif weight <= 2.0:
            rarity = "ðŸ”® RARE"
        elif weight <= 5.0:
            rarity = "ðŸŒŸ UNCOMMON"
        else:
            rarity = "âšª COMMON"

        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "transform",
            "damage": 0,
            "target_index": None,
            "form": user["meatwad_form"],
            "ts": _now_ts(),
        })

        self.state.save_state()
        self._log_event(f"Transform: @{username} became {form_name}.", battle=True)
        await ctx.send(f"ðŸ”„ {rarity} @{username} transformed into {form_name}! {description}")
        self._broadcast_state()

        await self._resolve_turn_if_ready(session)

    @commands.command(name="crack")
    async def crack(self, ctx):
        """Meatwad skill: Trigger BERZERK (enemies attack each other) or OVERDOSE (instant kill one enemy)."""
        username = ctx.author.name.lower()
        user = self.state.get_user(username)
        await self._play_media_fallback("crack", ctx)
        class_name = str(user.get("class_name", "")).strip().lower()
        if class_name != "meatwad" and username not in MEATWAD_ALIASES:
            return

        session = self.state.session()

        current_hp = int(user.get("hp_current", DEFAULT_PLAYER_HP))
        if current_hp <= 0:
            await ctx.send("You are knocked out and cannot act.")
            return

        if not user.get("active_player"):
            await ctx.send("You must join the battle first.")
            return
        if not session.get("battle_active"):
            await ctx.send("No active battle.")
            return
        if session.get("phase") != "action":
            await ctx.send("Action window is closed.")
            return

        participants = session.setdefault("participants", [])
        if username not in participants:
            await ctx.send("You must !join before acting.")
            return

        action_queue = session.get("action_queue", [])
        if any(entry.get("user") == username for entry in action_queue):
            await ctx.send("You already queued an action this turn.")
            return

        effect_type = "berzerk" if random.random() < MEATWAD_CRACK_BERZERK_CHANCE else "overdose"
        session.setdefault("action_queue", []).append({
            "user": username,
            "action": "crack",
            "effect_type": effect_type,
            "damage": 0,
            "target_index": None,
            "ts": _now_ts(),
        })

        self.state.save_state()
        if effect_type == "berzerk":
            self._log_event(f"Queued: @{username} triggered crack (berzerk).", battle=True)
            await ctx.send(f"@{username} hit crack: BERZERK primed. Enemies may turn on each other!")
        else:
            self._log_event(f"Queued: @{username} triggered crack (overdose).", battle=True)
            await ctx.send(f"@{username} hit crack: OVERDOSE primed. One enemy may drop instantly!")
        self._broadcast_state()

        await self._resolve_turn_if_ready(session)


# Core RPG cog class; methods are attached from module-level callables for resilience after reloads
class RpgCog(commands.Cog):
    _commands: dict = {}


# Attach all module-level callables (excluding helpers we don't want as methods) onto RpgCog
_EXCLUDE_METHOD_NAMES = {
    "prepare",
    "_iter_additional_commands",
    "_bind_additional_commands",
    "RpgCog",
    "RpgState",
}

for _name, _obj in list(globals().items()):
    if _name in _EXCLUDE_METHOD_NAMES:
        continue
    if callable(_obj):
        setattr(RpgCog, _name, _obj)


def _iter_additional_commands(cog):
    if not cog:
        return
    seen = set()
    state_instance = getattr(cog, "state", None)

    def _yield_from_container(container, instance):
        for member in container:
            if not isinstance(member, commands.Command):
                continue
            # Always rebind; prior reloads may leave _instance/cog set.
            if member.name in seen:
                continue
            seen.add(member.name)
            yield member, instance

    # Bind commands defined as class attributes on RpgCog (decorated methods become Command objects).
    yield from _yield_from_container(getattr(RpgCog, "__dict__", {}).values(), cog)

    # Some command definitions currently live on RpgState; bind them to the cog too.
    yield from _yield_from_container(getattr(RpgState, "__dict__", {}).values(), cog)

    # Module-level commands (rare) should run with the cog instance.
    yield from _yield_from_container(globals().values(), cog)


def _bind_additional_commands(bot, cog):
    logger = logging.getLogger("rpg")
    bound = []
    for command, instance in _iter_additional_commands(cog):
        # Ensure we replace any stale registration for this name.
        try:
            bot.remove_command(command.name)
        except Exception:
            pass
        command._instance = instance
        command.cog = cog
        cog._commands[command.name] = command
        try:
            bot.add_command(command)
            bound.append(command.name)
        except Exception as exc:
            logger.error(f"[RPG] Failed to bind module command {command.name}: {exc}")
    if bound:
        logger.info(f"[RPG] Bound module commands: {', '.join(bound)}")

# Expose state-implemented helpers on the cog so class lookups succeed
for _helper_name in (
    "_battle_loop_impl",
    "_queue_monster_action",
    "_is_user_revenant",
    "_is_revenant_pass_due",
    "_normalize_revenant_user",
    "_expire_revenant",
    "_set_revenant",
    "_grant_revenant_by_chance",
    "_transfer_revenant",
):
    if not hasattr(RpgCog, _helper_name) and hasattr(RpgState, _helper_name):
        setattr(RpgCog, _helper_name, getattr(RpgState, _helper_name))

# Backfill any remaining callable helpers from RpgState onto RpgCog
for _name, _obj in RpgState.__dict__.items():
    if _name.startswith("__"):
        continue
    if hasattr(RpgCog, _name):
        continue
    if callable(_obj):
        setattr(RpgCog, _name, _obj)

# Ensure RpgState exposes _state_obj for mis-bound helpers
if not hasattr(RpgState, "_state_obj"):
    def _state_obj(self):
        return self
    RpgState._state_obj = _state_obj


def prepare(bot):
    print("[RPG] prepare(bot) called for RpgCog")
    logging.getLogger("rpg").info("[RPG] prepare(bot) called for RpgCog")
    if not bot.get_cog("RpgCog"):
        print("[RPG] Adding RpgCog to bot...")
        logging.getLogger("rpg").info("[RPG] Adding RpgCog to bot...")
        # Avoid conflicts with media/SFX commands that may reserve the same name
        try:
            bot.remove_command("fight")
        except Exception:
            pass
        cog = RpgCog(bot)
        bot.add_cog(cog)
        _bind_additional_commands(bot, cog)
        print("[DEBUG] dropship command should now be registered.")
        logging.getLogger("rpg").info("[DEBUG] dropship command registered.")
