"""Versioned data contracts for Stream RPG v2.

These contracts are deliberately small. They define persistence and transport
boundaries, not combat implementation details. The pure battle engine will
consume and produce these shapes without importing Twitch, OBS, or legacy RPG
code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


CONTRACT_VERSION = 1
PLAYER_SCHEMA = "rpg_v2.player"
RUNTIME_SCHEMA = "rpg_v2.runtime"
EVENT_SCHEMA = "rpg_v2.animation_event"


class CharacterClass(StrEnum):
    ADVENTURER = "adventurer"
    WARRIOR = "warrior"
    MAGE = "mage"
    HEALER = "healer"
    RANGER = "ranger"


class RuntimePhase(StrEnum):
    IDLE = "idle"
    WANDER = "wander"
    ENCOUNTER_INTRO = "encounter_intro"
    ACTION_PLAYBACK = "action_playback"
    CHECK = "check"
    VICTORY = "victory"
    DEFEAT = "defeat"
    RESULTS = "results"
    PAUSED = "paused"


class EventType(StrEnum):
    ACTOR_JOINED = "actor_joined"
    ACTOR_LEFT = "actor_left"
    ENCOUNTER_STARTED = "encounter_started"
    ACTION_STARTED = "action_started"
    PROJECTILE_SPAWNED = "projectile_spawned"
    DAMAGE_APPLIED = "damage_applied"
    HEALING_APPLIED = "healing_applied"
    ACTOR_DEFEATED = "actor_defeated"
    BATTLE_FINISHED = "battle_finished"
    LOOT_AWARDED = "loot_awarded"
    LEVEL_GAINED = "level_gained"
    CLASS_ADVANCED = "class_advanced"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _require_schema(record: Mapping[str, Any], expected: str) -> None:
    _require(record.get("schema") == expected, f"expected schema {expected!r}")
    _require(record.get("version") == CONTRACT_VERSION, f"expected version {CONTRACT_VERSION}")


def new_player_record(viewer_id: str, display_name: str, *, now: str | None = None) -> dict[str, Any]:
    """Return the minimal persisted record for a newly joined viewer."""

    timestamp = now or _utc_now()
    record: dict[str, Any] = {
        "schema": PLAYER_SCHEMA,
        "version": CONTRACT_VERSION,
        "viewer_id": str(viewer_id).strip(),
        "display_name": str(display_name).strip(),
        "class": CharacterClass.ADVENTURER.value,
        "level": 1,
        "xp": 0,
        "cosmetics": {"palette": "default", "title": None},
        "history": {"battles": 0, "victories": 0, "boss_victories": 0},
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    validate_player_record(record)
    return record


def validate_player_record(record: Mapping[str, Any]) -> None:
    _require_schema(record, PLAYER_SCHEMA)
    _require(bool(str(record.get("viewer_id", "")).strip()), "viewer_id is required")
    _require(bool(str(record.get("display_name", "")).strip()), "display_name is required")
    _require(record.get("class") in {item.value for item in CharacterClass}, "unknown character class")
    _require(isinstance(record.get("level"), int) and record["level"] >= 1, "level must be >= 1")
    _require(isinstance(record.get("xp"), int) and record["xp"] >= 0, "xp must be >= 0")
    _require(isinstance(record.get("cosmetics"), Mapping), "cosmetics must be an object")
    history = record.get("history")
    _require(isinstance(history, Mapping), "history must be an object")
    for key in ("battles", "victories", "boss_victories"):
        _require(isinstance(history.get(key), int) and history[key] >= 0, f"history.{key} must be >= 0")


def new_runtime_snapshot(*, now: str | None = None) -> dict[str, Any]:
    """Return a recoverable empty runtime snapshot.

    Presence timestamps are runtime concerns and intentionally do not live in
    persisted player records.
    """

    record: dict[str, Any] = {
        "schema": RUNTIME_SCHEMA,
        "version": CONTRACT_VERSION,
        "updated_at": now or _utc_now(),
        "battle_id": None,
        "phase": RuntimePhase.WANDER.value,
        "round": 0,
        "active_party": [],
        "reserve_count": 0,
        "enemies": [],
        "last_event_sequence": 0,
        "result": None,
    }
    validate_runtime_snapshot(record)
    return record


def validate_runtime_snapshot(record: Mapping[str, Any]) -> None:
    _require_schema(record, RUNTIME_SCHEMA)
    _require(record.get("phase") in {item.value for item in RuntimePhase}, "unknown runtime phase")
    _require(isinstance(record.get("round"), int) and record["round"] >= 0, "round must be >= 0")
    _require(isinstance(record.get("active_party"), list), "active_party must be a list")
    _require(len(record["active_party"]) <= 4, "active_party cannot exceed four actors")
    _require(isinstance(record.get("reserve_count"), int) and record["reserve_count"] >= 0, "reserve_count must be >= 0")
    _require(isinstance(record.get("enemies"), list), "enemies must be a list")
    _require(len(record["enemies"]) <= 3, "enemies cannot exceed three actors")
    _require(
        isinstance(record.get("last_event_sequence"), int) and record["last_event_sequence"] >= 0,
        "last_event_sequence must be >= 0",
    )


def new_animation_event(
    event_type: EventType | str,
    *,
    battle_id: str,
    round_number: int,
    sequence: int,
    actor_id: str | None = None,
    target_ids: list[str] | None = None,
    effect: str | None = None,
    values: Mapping[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Create one idempotently ordered overlay animation event."""

    kind = event_type.value if isinstance(event_type, EventType) else str(event_type)
    record: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "version": CONTRACT_VERSION,
        "created_at": now or _utc_now(),
        "battle_id": str(battle_id).strip(),
        "round": round_number,
        "sequence": sequence,
        "type": kind,
        "actor_id": actor_id,
        "target_ids": list(target_ids or []),
        "effect": effect,
        "values": dict(values or {}),
    }
    validate_animation_event(record)
    return record


def validate_animation_event(record: Mapping[str, Any]) -> None:
    _require_schema(record, EVENT_SCHEMA)
    _require(bool(str(record.get("battle_id", "")).strip()), "battle_id is required")
    _require(isinstance(record.get("round"), int) and record["round"] >= 0, "round must be >= 0")
    _require(isinstance(record.get("sequence"), int) and record["sequence"] >= 1, "sequence must be >= 1")
    _require(record.get("type") in {item.value for item in EventType}, "unknown animation event type")
    _require(isinstance(record.get("target_ids"), list), "target_ids must be a list")
    _require(isinstance(record.get("values"), Mapping), "values must be an object")
