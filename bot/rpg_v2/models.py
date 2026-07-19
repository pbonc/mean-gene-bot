"""Pure domain models for Stream RPG v2 combat."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Side(StrEnum):
    FRIENDLY = "friendly"
    ENEMY = "enemy"


class EffectKind(StrEnum):
    DAMAGE = "damage"
    HEAL = "heal"
    SHIELD = "shield"
    FOCUS = "focus"
    MARK = "mark"


@dataclass(frozen=True)
class Skill:
    number: int
    skill_id: str
    label: str
    effect: EffectKind
    amount: int
    target: str


@dataclass
class Actor:
    actor_id: str
    name: str
    kind: str
    side: Side
    max_hp: int
    speed: int
    hp: int | None = None
    shield: int = 0
    power_bonus: int = 0
    marked_bonus: int = 0

    def __post_init__(self):
        self.actor_id = str(self.actor_id).strip()
        self.name = str(self.name).strip()
        if not self.actor_id or not self.name:
            raise ValueError("actor_id and name are required")
        if self.max_hp <= 0 or self.speed <= 0:
            raise ValueError("max_hp and speed must be positive")
        if self.hp is None:
            self.hp = self.max_hp
        if self.hp < 0 or self.hp > self.max_hp:
            raise ValueError("hp must be between zero and max_hp")

    @property
    def alive(self) -> bool:
        return bool(self.hp and self.hp > 0)

    @property
    def missing_hp(self) -> int:
        return self.max_hp - int(self.hp or 0)

    def clone(self) -> "Actor":
        return Actor(
            actor_id=self.actor_id,
            name=self.name,
            kind=self.kind,
            side=self.side,
            max_hp=self.max_hp,
            speed=self.speed,
            hp=self.hp,
            shield=self.shield,
            power_bonus=self.power_bonus,
            marked_bonus=self.marked_bonus,
        )

    def overlay_record(self) -> dict:
        return {
            "actor_id": self.actor_id,
            "name": self.name,
            "kind": self.kind,
            "side": self.side.value,
            "hp": int(self.hp or 0),
            "max_hp": self.max_hp,
            "shield": self.shield,
            "alive": self.alive,
        }


@dataclass
class BattleResult:
    outcome: str
    rounds: int
    turns: int
    events: list[dict] = field(default_factory=list)
