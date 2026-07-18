"""Initial enemy kits and deterministic behavior."""

from __future__ import annotations

from .models import Actor, EffectKind, Skill


ENEMY_KITS: dict[str, tuple[Skill, ...]] = {
    "slime": (Skill(1, "slime_bump", "Bump", EffectKind.DAMAGE, 6, "weakest_enemy"),),
    "goblin": (
        Skill(1, "goblin_stab", "Stab", EffectKind.DAMAGE, 8, "weakest_enemy"),
        Skill(2, "goblin_guard", "Guard", EffectKind.SHIELD, 7, "self"),
    ),
    "ogre": (
        Skill(1, "ogre_smash", "Smash", EffectKind.DAMAGE, 13, "weakest_enemy"),
        Skill(2, "ogre_sweep", "Sweeping Blow", EffectKind.DAMAGE, 7, "all_enemies"),
    ),
}


def enemy_skills(kind: str) -> tuple[Skill, ...]:
    try:
        return ENEMY_KITS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown enemy kind: {kind}") from exc


def default_enemy_choice(actor: Actor, round_number: int) -> int:
    if actor.kind == "goblin" and round_number % 3 == 0:
        return 2
    if actor.kind == "ogre" and round_number % 2 == 0:
        return 2
    return 1
