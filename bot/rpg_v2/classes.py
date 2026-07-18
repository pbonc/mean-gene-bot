"""Initial friendly class kits and default-action policies."""

from __future__ import annotations

from .contracts import CharacterClass
from .models import Actor, EffectKind, Skill


FRIENDLY_KITS: dict[str, tuple[Skill, Skill, Skill]] = {
    CharacterClass.ADVENTURER.value: (
        Skill(1, "strike", "Strike", EffectKind.DAMAGE, 8, "weakest_enemy"),
        Skill(2, "brace", "Brace", EffectKind.SHIELD, 8, "self"),
        Skill(3, "rally", "Rally", EffectKind.SHIELD, 3, "all_allies"),
    ),
    CharacterClass.WARRIOR.value: (
        Skill(1, "slash", "Slash", EffectKind.DAMAGE, 10, "strongest_enemy"),
        Skill(2, "guard_ally", "Guard Ally", EffectKind.SHIELD, 10, "lowest_ally"),
        Skill(3, "shield_slam", "Shield Slam", EffectKind.DAMAGE, 15, "strongest_enemy"),
    ),
    CharacterClass.MAGE.value: (
        Skill(1, "arcane_bolt", "Arcane Bolt", EffectKind.DAMAGE, 12, "strongest_enemy"),
        Skill(2, "fireball", "Fireball", EffectKind.DAMAGE, 7, "all_enemies"),
        Skill(3, "focus", "Focus", EffectKind.FOCUS, 7, "self"),
    ),
    CharacterClass.HEALER.value: (
        Skill(1, "smite", "Smite", EffectKind.DAMAGE, 8, "weakest_enemy"),
        Skill(2, "heal", "Heal", EffectKind.HEAL, 13, "lowest_ally"),
        Skill(3, "group_heal", "Group Heal", EffectKind.HEAL, 6, "all_allies"),
    ),
    CharacterClass.RANGER.value: (
        Skill(1, "quick_shot", "Quick Shot", EffectKind.DAMAGE, 10, "weakest_enemy"),
        Skill(2, "mark_target", "Mark Target", EffectKind.MARK, 4, "strongest_enemy"),
        Skill(3, "volley", "Volley", EffectKind.DAMAGE, 6, "all_enemies"),
    ),
}


def friendly_skills(kind: str) -> tuple[Skill, Skill, Skill]:
    try:
        return FRIENDLY_KITS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown friendly class: {kind}") from exc


def default_friendly_choice(actor: Actor, allies: list[Actor]) -> int:
    if actor.kind == CharacterClass.HEALER.value:
        wounded = [ally for ally in allies if ally.alive and ally.missing_hp > 0]
        if wounded:
            return 2
    return 1
