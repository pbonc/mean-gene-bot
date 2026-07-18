"""Stream RPG v2 domain package.

This package must remain independent of ``archive.rpg`` and Twitch/overlay adapters.
"""

from .contracts import (
    CONTRACT_VERSION,
    CharacterClass,
    EventType,
    RuntimePhase,
    new_animation_event,
    new_expedition_snapshot,
    new_player_record,
    new_runtime_snapshot,
    new_turn_prompt,
    validate_animation_event,
    validate_expedition_snapshot,
    validate_player_record,
    validate_runtime_snapshot,
    validate_turn_prompt,
)
from .engine import BattleEngine, make_enemy, make_friendly
from .models import Actor, BattleResult, EffectKind, Side, Skill

__all__ = [
    "CONTRACT_VERSION",
    "CharacterClass",
    "EventType",
    "RuntimePhase",
    "new_animation_event",
    "new_expedition_snapshot",
    "new_player_record",
    "new_runtime_snapshot",
    "new_turn_prompt",
    "validate_animation_event",
    "validate_expedition_snapshot",
    "validate_player_record",
    "validate_runtime_snapshot",
    "validate_turn_prompt",
    "Actor",
    "BattleEngine",
    "BattleResult",
    "EffectKind",
    "Side",
    "Skill",
    "make_enemy",
    "make_friendly",
]
