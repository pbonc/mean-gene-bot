"""Stream RPG v2 domain package.

This package must remain independent of ``archive.rpg`` and Twitch/overlay adapters.
"""

from .contracts import (
    CONTRACT_VERSION,
    CharacterClass,
    EventType,
    RuntimePhase,
    new_animation_event,
    new_player_record,
    new_runtime_snapshot,
    new_turn_prompt,
    validate_animation_event,
    validate_player_record,
    validate_runtime_snapshot,
    validate_turn_prompt,
)

__all__ = [
    "CONTRACT_VERSION",
    "CharacterClass",
    "EventType",
    "RuntimePhase",
    "new_animation_event",
    "new_player_record",
    "new_runtime_snapshot",
    "new_turn_prompt",
    "validate_animation_event",
    "validate_player_record",
    "validate_runtime_snapshot",
    "validate_turn_prompt",
]
