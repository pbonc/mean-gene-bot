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
    validate_animation_event,
    validate_player_record,
    validate_runtime_snapshot,
)

__all__ = [
    "CONTRACT_VERSION",
    "CharacterClass",
    "EventType",
    "RuntimePhase",
    "new_animation_event",
    "new_player_record",
    "new_runtime_snapshot",
    "validate_animation_event",
    "validate_player_record",
    "validate_runtime_snapshot",
]
