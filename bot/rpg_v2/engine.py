"""Deterministic, presentation-independent Stream RPG v2 turn engine."""

from __future__ import annotations

import random
from collections.abc import Iterable

from .classes import default_friendly_choice, friendly_skills
from .contracts import EventType, new_animation_event, new_turn_prompt
from .enemies import default_enemy_choice, enemy_skills
from .models import Actor, BattleResult, EffectKind, Side, Skill


FRIENDLY_STATS = {
    "adventurer": (36, 10),
    "warrior": (50, 7),
    "mage": (31, 11),
    "healer": (38, 8),
    "ranger": (34, 13),
}

ENEMY_STATS = {
    "slime": (24, 6),
    "goblin": (34, 9),
    "ogre": (95, 5),
}


def make_friendly(actor_id: str, name: str, kind: str = "adventurer") -> Actor:
    try:
        hp, speed = FRIENDLY_STATS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown friendly class: {kind}") from exc
    return Actor(actor_id, name, kind, Side.FRIENDLY, hp, speed)


def make_enemy(actor_id: str, name: str, kind: str) -> Actor:
    try:
        hp, speed = ENEMY_STATS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown enemy kind: {kind}") from exc
    return Actor(actor_id, name, kind, Side.ENEMY, hp, speed)


class BattleEngine:
    """Resolve one actor at a time and emit ordered animation events."""

    def __init__(self, battle_id: str, friendlies: Iterable[Actor], enemies: Iterable[Actor], *, seed: int = 0):
        self.battle_id = str(battle_id).strip()
        if not self.battle_id:
            raise ValueError("battle_id is required")
        self.friendlies = [actor.clone() for actor in friendlies]
        self.enemies = [actor.clone() for actor in enemies]
        if not self.friendlies or not self.enemies:
            raise ValueError("battle requires at least one actor on each side")
        if any(actor.side is not Side.FRIENDLY for actor in self.friendlies):
            raise ValueError("friendly roster contains a non-friendly actor")
        if any(actor.side is not Side.ENEMY for actor in self.enemies):
            raise ValueError("enemy roster contains a non-enemy actor")
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("actor IDs must be unique")

        self.rng = random.Random(seed)
        self.round_number = 0
        self.turns_resolved = 0
        self.outcome: str | None = None
        self.events: list[dict] = []
        self._event_sequence = 0
        self._turn_queue: list[str] = []
        self._finished_event_emitted = False
        self._prompted_turn_ids: set[str] = set()

    @property
    def actors(self) -> list[Actor]:
        return [*self.friendlies, *self.enemies]

    def actor_by_id(self, actor_id: str) -> Actor:
        for actor in self.actors:
            if actor.actor_id == actor_id:
                return actor
        raise KeyError(actor_id)

    def living(self, side: Side) -> list[Actor]:
        roster = self.friendlies if side is Side.FRIENDLY else self.enemies
        return [actor for actor in roster if actor.alive]

    def current_actor(self) -> Actor | None:
        if self.outcome:
            return None
        while True:
            while self._turn_queue:
                actor = self.actor_by_id(self._turn_queue[0])
                if actor.alive:
                    return actor
                self._turn_queue.pop(0)
            self._start_round()
            if not self._turn_queue:
                self._set_outcome(self._check_outcome() or "stalemate")
                return None

    def _start_round(self):
        outcome = self._check_outcome()
        if outcome:
            self._set_outcome(outcome)
            return
        self.round_number += 1
        living = [actor for actor in self.actors if actor.alive]
        living.sort(key=lambda actor: (-actor.speed, 0 if actor.side is Side.FRIENDLY else 1, actor.actor_id))
        self._turn_queue = [actor.actor_id for actor in living]

    def turn_prompt(self, *, waits_for_viewer: bool, deadline: str | None = None) -> dict:
        actor = self.current_actor()
        if actor is None or actor.side is not Side.FRIENDLY:
            raise ValueError("current actor is not a friendly viewer")
        skills = friendly_skills(actor.kind)
        default_choice = default_friendly_choice(actor, self.friendlies)
        prompt = new_turn_prompt(
            battle_id=self.battle_id,
            turn_id=f"{self.battle_id}:r{self.round_number}:{actor.actor_id}",
            actor_id=actor.actor_id,
            choices=[{"number": skill.number, "skill_id": skill.skill_id, "label": skill.label} for skill in skills],
            default_choice=default_choice,
            waits_for_viewer=waits_for_viewer,
            deadline=deadline,
        )
        if prompt["turn_id"] not in self._prompted_turn_ids:
            self._prompted_turn_ids.add(prompt["turn_id"])
            self._emit(
                EventType.TURN_PROMPTED,
                actor_id=actor.actor_id,
                values={
                    "turn_id": prompt["turn_id"],
                    "choices": prompt["choices"],
                    "default_choice": prompt["default_choice"],
                    "waits_for_viewer": prompt["waits_for_viewer"],
                    "deadline": prompt["deadline"],
                },
            )
        return prompt

    def resolve_current_turn(self, choice_number: int | None = None) -> list[dict]:
        actor = self.current_actor()
        if actor is None:
            return []
        event_start = len(self.events)

        if actor.side is Side.FRIENDLY:
            skills = friendly_skills(actor.kind)
            default_choice = default_friendly_choice(actor, self.friendlies)
        else:
            skills = enemy_skills(actor.kind)
            default_choice = default_enemy_choice(actor, self.round_number)

        selected_number = default_choice if choice_number is None else choice_number
        selected = next((skill for skill in skills if skill.number == selected_number), None)
        if selected is None:
            raise ValueError(f"invalid skill choice {selected_number} for {actor.kind}")
        defaulted = choice_number is None

        self._emit(
            EventType.DEFAULT_SELECTED if defaulted else EventType.SKILL_SELECTED,
            actor_id=actor.actor_id,
            effect=selected.skill_id,
            values={"choice": selected.number, "label": selected.label, "defaulted": defaulted},
        )
        self._emit(
            EventType.ACTION_STARTED,
            actor_id=actor.actor_id,
            effect=selected.skill_id,
            values={"label": selected.label},
        )
        self._apply_skill(actor, selected)
        self.turns_resolved += 1
        if self._turn_queue and self._turn_queue[0] == actor.actor_id:
            self._turn_queue.pop(0)
        outcome = self._check_outcome()
        if outcome:
            self._set_outcome(outcome)
        return self.events[event_start:]

    def _targets_for(self, actor: Actor, skill: Skill) -> list[Actor]:
        allies = self.living(actor.side)
        opposing_side = Side.ENEMY if actor.side is Side.FRIENDLY else Side.FRIENDLY
        opponents = self.living(opposing_side)
        if skill.target == "self":
            return [actor]
        if skill.target == "all_allies":
            return allies
        if skill.target == "all_enemies":
            return opponents
        if skill.target == "lowest_ally":
            return [min(allies, key=lambda target: (target.hp / target.max_hp, target.actor_id))] if allies else []
        if skill.target == "weakest_enemy":
            return [min(opponents, key=lambda target: (target.hp, target.actor_id))] if opponents else []
        if skill.target == "strongest_enemy":
            return [max(opponents, key=lambda target: (target.hp, target.actor_id))] if opponents else []
        raise ValueError(f"unknown target policy: {skill.target}")

    def _apply_skill(self, actor: Actor, skill: Skill):
        targets = self._targets_for(actor, skill)
        if not targets:
            return
        if skill.effect is EffectKind.FOCUS:
            actor.power_bonus += skill.amount
            self._emit(EventType.STATUS_APPLIED, actor_id=actor.actor_id, target_ids=[actor.actor_id], effect=skill.skill_id, values={"power_bonus": skill.amount})
            return
        action_power_bonus = actor.power_bonus if skill.effect is EffectKind.DAMAGE else 0
        if skill.effect is EffectKind.DAMAGE:
            actor.power_bonus = 0
        for target in targets:
            if skill.effect is EffectKind.DAMAGE:
                rolled = max(1, skill.amount + action_power_bonus + self.rng.randint(-1, 1) + target.marked_bonus)
                target.marked_bonus = 0
                absorbed = min(target.shield, rolled)
                target.shield -= absorbed
                dealt = max(0, rolled - absorbed)
                target.hp = max(0, int(target.hp or 0) - dealt)
                self._emit(EventType.DAMAGE_APPLIED, actor_id=actor.actor_id, target_ids=[target.actor_id], effect=skill.skill_id, values={"damage": dealt, "absorbed": absorbed})
                if not target.alive:
                    self._emit(EventType.ACTOR_DEFEATED, actor_id=actor.actor_id, target_ids=[target.actor_id], effect=skill.skill_id)
            elif skill.effect is EffectKind.HEAL:
                healed = min(skill.amount, target.missing_hp)
                target.hp = int(target.hp or 0) + healed
                self._emit(EventType.HEALING_APPLIED, actor_id=actor.actor_id, target_ids=[target.actor_id], effect=skill.skill_id, values={"healing": healed})
            elif skill.effect is EffectKind.SHIELD:
                target.shield += skill.amount
                self._emit(EventType.SHIELD_APPLIED, actor_id=actor.actor_id, target_ids=[target.actor_id], effect=skill.skill_id, values={"shield": skill.amount})
            elif skill.effect is EffectKind.MARK:
                target.marked_bonus = max(target.marked_bonus, skill.amount)
                self._emit(EventType.STATUS_APPLIED, actor_id=actor.actor_id, target_ids=[target.actor_id], effect=skill.skill_id, values={"marked_bonus": skill.amount})

    def _check_outcome(self) -> str | None:
        if not self.living(Side.ENEMY):
            return "victory"
        if not self.living(Side.FRIENDLY):
            return "defeat"
        return None

    def _set_outcome(self, outcome: str):
        self.outcome = outcome
        if not self._finished_event_emitted:
            self._finished_event_emitted = True
            self._emit(EventType.BATTLE_FINISHED, values={"outcome": outcome})

    def _emit(self, event_type: EventType, *, actor_id: str | None = None, target_ids: list[str] | None = None, effect: str | None = None, values: dict | None = None):
        self._event_sequence += 1
        self.events.append(
            new_animation_event(
                event_type,
                battle_id=self.battle_id,
                round_number=self.round_number,
                sequence=self._event_sequence,
                actor_id=actor_id,
                target_ids=target_ids,
                effect=effect,
                values=values,
                now="1970-01-01T00:00:00Z",
            )
        )

    def run_to_completion(self, *, max_rounds: int = 200) -> BattleResult:
        if max_rounds <= 0:
            raise ValueError("max_rounds must be positive")
        while not self.outcome:
            self.resolve_current_turn()
            if not self.outcome and self.round_number >= max_rounds and not self._turn_queue:
                self._set_outcome("stalemate")
        return BattleResult(self.outcome, self.round_number, self.turns_resolved, list(self.events))
