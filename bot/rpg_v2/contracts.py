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


CONTRACT_VERSION = 2
PLAYER_SCHEMA = "rpg_v2.player"
RUNTIME_SCHEMA = "rpg_v2.runtime"
EVENT_SCHEMA = "rpg_v2.animation_event"
TURN_PROMPT_SCHEMA = "rpg_v2.turn_prompt"
EXPEDITION_SCHEMA = "rpg_v2.expedition"
BATTLE_OVERLAY_SCHEMA = "rpg_v2.battle_overlay"


class CharacterClass(StrEnum):
    ADVENTURER = "adventurer"
    WARRIOR = "warrior"
    MAGE = "mage"
    HEALER = "healer"
    RANGER = "ranger"


class RuntimePhase(StrEnum):
    JOURNEY = "journey"
    ENCOUNTER_READY = "encounter_ready"
    BATTLE_STARTING = "battle_starting"
    ACTOR_CHOICE = "actor_choice"
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
    ENCOUNTER_READY = "encounter_ready"
    TURN_PROMPTED = "turn_prompted"
    SKILL_SELECTED = "skill_selected"
    DEFAULT_SELECTED = "default_selected"
    ACTION_STARTED = "action_started"
    PROJECTILE_SPAWNED = "projectile_spawned"
    DAMAGE_APPLIED = "damage_applied"
    HEALING_APPLIED = "healing_applied"
    SHIELD_APPLIED = "shield_applied"
    STATUS_APPLIED = "status_applied"
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


def new_expedition_snapshot(
    members: list[Mapping[str, Any]],
    *,
    active_window_seconds: int,
    walkoff_window_seconds: int,
    now: str | None = None,
) -> dict[str, Any]:
    """Create the live, non-persisted expedition payload used by the strip."""

    record: dict[str, Any] = {
        "type": "rpg_v2_expedition",
        "schema": EXPEDITION_SCHEMA,
        "version": CONTRACT_VERSION,
        "generated_at": now or _utc_now(),
        "active_window_seconds": active_window_seconds,
        "walkoff_window_seconds": walkoff_window_seconds,
        "members": [dict(member) for member in members],
    }
    validate_expedition_snapshot(record)
    return record


def validate_expedition_snapshot(record: Mapping[str, Any]) -> None:
    _require_schema(record, EXPEDITION_SCHEMA)
    _require(record.get("type") == "rpg_v2_expedition", "unexpected expedition payload type")
    active_window = record.get("active_window_seconds")
    walkoff_window = record.get("walkoff_window_seconds")
    _require(isinstance(active_window, int) and active_window > 0, "active_window_seconds must be positive")
    _require(isinstance(walkoff_window, int) and walkoff_window > active_window, "walkoff window must exceed active window")
    members = record.get("members")
    _require(isinstance(members, list), "members must be a list")
    _require_unique_ids(members, "members")
    for member_record in members:
        _require(bool(str(member_record.get("display_name", "")).strip()), "member display_name is required")
        _require(member_record.get("class") in {item.value for item in CharacterClass}, "unknown member class")
        _require(member_record.get("presence") in ("active", "idle"), "member presence must be active or idle")
        _require(isinstance(member_record.get("last_seen_at"), (int, float)), "member last_seen_at must be numeric")


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
        "phase": RuntimePhase.JOURNEY.value,
        "round": 0,
        "expedition": [],
        "participants": [],
        "enemies": [],
        "pending_turn": None,
        "last_event_sequence": 0,
        "result": None,
    }
    validate_runtime_snapshot(record)
    return record


def validate_runtime_snapshot(record: Mapping[str, Any]) -> None:
    _require_schema(record, RUNTIME_SCHEMA)
    _require(record.get("phase") in {item.value for item in RuntimePhase}, "unknown runtime phase")
    _require(isinstance(record.get("round"), int) and record["round"] >= 0, "round must be >= 0")
    _require(isinstance(record.get("expedition"), list), "expedition must be a list")
    _require(isinstance(record.get("participants"), list), "participants must be a list")
    _require(isinstance(record.get("enemies"), list), "enemies must be a list")
    _require_unique_ids(record["expedition"], "expedition")
    _require_unique_ids(record["participants"], "participants")
    _require_unique_ids(record["enemies"], "enemies")
    pending_turn = record.get("pending_turn")
    _require(pending_turn is None or isinstance(pending_turn, Mapping), "pending_turn must be null or an object")
    if pending_turn is not None:
        validate_turn_prompt(pending_turn)
        _require(pending_turn.get("battle_id") == record.get("battle_id"), "pending_turn battle_id must match runtime")
        participant_ids = {str(item.get("actor_id")) for item in record["participants"]}
        _require(pending_turn.get("actor_id") in participant_ids, "pending_turn actor must be a participant")
    if record.get("phase") == RuntimePhase.ACTOR_CHOICE.value:
        _require(pending_turn is not None, "actor_choice phase requires pending_turn")
    _require(
        isinstance(record.get("last_event_sequence"), int) and record["last_event_sequence"] >= 0,
        "last_event_sequence must be >= 0",
    )


def _require_unique_ids(items: list[Any], field_name: str) -> None:
    ids: list[str] = []
    for item in items:
        _require(isinstance(item, Mapping), f"{field_name} entries must be objects")
        actor_id = str(item.get("actor_id", "")).strip()
        _require(bool(actor_id), f"{field_name} actor_id is required")
        ids.append(actor_id)
    _require(len(ids) == len(set(ids)), f"{field_name} actor_id values must be unique")


def new_turn_prompt(
    *,
    battle_id: str,
    turn_id: str,
    actor_id: str,
    choices: list[Mapping[str, Any]],
    default_choice: int,
    waits_for_viewer: bool,
    deadline: str | None = None,
) -> dict[str, Any]:
    """Create the three-choice contract shown to one acting viewer.

    ``deadline`` is null when the actor should auto-act immediately. The engine
    applies ``default_choice`` when no accepted selection exists by the deadline.
    """

    record: dict[str, Any] = {
        "schema": TURN_PROMPT_SCHEMA,
        "version": CONTRACT_VERSION,
        "battle_id": str(battle_id).strip(),
        "turn_id": str(turn_id).strip(),
        "actor_id": str(actor_id).strip(),
        "choices": [dict(choice) for choice in choices],
        "default_choice": default_choice,
        "waits_for_viewer": waits_for_viewer,
        "deadline": deadline,
    }
    validate_turn_prompt(record)
    return record


def validate_turn_prompt(record: Mapping[str, Any]) -> None:
    _require_schema(record, TURN_PROMPT_SCHEMA)
    for field in ("battle_id", "turn_id", "actor_id"):
        _require(bool(str(record.get(field, "")).strip()), f"{field} is required")
    choices = record.get("choices")
    _require(isinstance(choices, list), "choices must be a list")
    _require(len(choices) == 3, "turn prompt requires exactly three choices")
    numbers: list[int] = []
    for choice in choices:
        _require(isinstance(choice, Mapping), "choice entries must be objects")
        number = choice.get("number")
        _require(isinstance(number, int), "choice number must be an integer")
        numbers.append(number)
        _require(bool(str(choice.get("skill_id", "")).strip()), "choice skill_id is required")
        _require(bool(str(choice.get("label", "")).strip()), "choice label is required")
    _require(sorted(numbers) == [1, 2, 3], "choice numbers must be 1, 2, and 3")
    _require(record.get("default_choice") in (1, 2, 3), "default_choice must be 1, 2, or 3")
    _require(isinstance(record.get("waits_for_viewer"), bool), "waits_for_viewer must be boolean")
    deadline = record.get("deadline")
    _require(deadline is None or isinstance(deadline, str), "deadline must be null or a string")
    if record.get("waits_for_viewer"):
        _require(bool(deadline), "viewer choice requires a deadline")
    else:
        _require(deadline is None, "automatic choice must not wait on a deadline")


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


def new_battle_overlay_snapshot(
    *,
    battle_id: str | None,
    phase: RuntimePhase | str,
    round_number: int,
    friendlies: list[Mapping[str, Any]],
    enemies: list[Mapping[str, Any]],
    pending_turn: Mapping[str, Any] | None = None,
    last_event_sequence: int = 0,
    result: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Create the authoritative state consumed by the full-screen renderer."""

    phase_value = phase.value if isinstance(phase, RuntimePhase) else str(phase)
    record: dict[str, Any] = {
        "type": "rpg_v2_battle_snapshot",
        "schema": BATTLE_OVERLAY_SCHEMA,
        "version": CONTRACT_VERSION,
        "generated_at": now or _utc_now(),
        "battle_id": battle_id,
        "phase": phase_value,
        "round": round_number,
        "friendlies": [dict(actor) for actor in friendlies],
        "enemies": [dict(actor) for actor in enemies],
        "pending_turn": dict(pending_turn) if pending_turn else None,
        "last_event_sequence": last_event_sequence,
        "result": result,
    }
    validate_battle_overlay_snapshot(record)
    return record


def validate_battle_overlay_snapshot(record: Mapping[str, Any]) -> None:
    _require_schema(record, BATTLE_OVERLAY_SCHEMA)
    _require(record.get("type") == "rpg_v2_battle_snapshot", "unexpected battle payload type")
    _require(record.get("phase") in {item.value for item in RuntimePhase}, "unknown battle phase")
    _require(isinstance(record.get("round"), int) and record["round"] >= 0, "round must be >= 0")
    _require(isinstance(record.get("last_event_sequence"), int) and record["last_event_sequence"] >= 0, "last_event_sequence must be >= 0")
    friendlies = record.get("friendlies")
    enemies = record.get("enemies")
    _require(isinstance(friendlies, list), "friendlies must be a list")
    _require(isinstance(enemies, list), "enemies must be a list")
    _require_unique_ids([*friendlies, *enemies], "battle actors")
    for actor in [*friendlies, *enemies]:
        _require(bool(str(actor.get("name", "")).strip()), "actor name is required")
        _require(bool(str(actor.get("kind", "")).strip()), "actor kind is required")
        _require(actor.get("side") in ("friendly", "enemy"), "actor side must be friendly or enemy")
        max_hp = actor.get("max_hp")
        hp = actor.get("hp")
        _require(isinstance(max_hp, int) and max_hp > 0, "actor max_hp must be positive")
        _require(isinstance(hp, int) and 0 <= hp <= max_hp, "actor hp must be between zero and max_hp")
        _require(isinstance(actor.get("shield"), int) and actor["shield"] >= 0, "actor shield must be non-negative")
    pending_turn = record.get("pending_turn")
    _require(pending_turn is None or isinstance(pending_turn, Mapping), "pending_turn must be null or an object")
    if pending_turn is not None:
        validate_turn_prompt(pending_turn)
        _require(pending_turn.get("battle_id") == record.get("battle_id"), "pending_turn battle_id must match snapshot")
    if record.get("phase") == RuntimePhase.ACTOR_CHOICE.value:
        _require(pending_turn is not None, "actor_choice phase requires pending_turn")
