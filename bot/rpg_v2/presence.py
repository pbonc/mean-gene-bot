"""In-memory Twitch presence for the Stream RPG v2 expedition."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .contracts import CharacterClass, new_expedition_snapshot


@dataclass
class ExpeditionMember:
    actor_id: str
    display_name: str
    joined_at: float
    last_seen_at: float
    character_class: str = CharacterClass.ADVENTURER.value


class ExpeditionPresenceService:
    """Track joined viewers without persistence or battle responsibilities."""

    def __init__(
        self,
        *,
        active_window_seconds: int = 20 * 60,
        walkoff_window_seconds: int = 45 * 60,
        clock: Callable[[], float] = time.time,
    ):
        if active_window_seconds <= 0:
            raise ValueError("active_window_seconds must be positive")
        if walkoff_window_seconds <= active_window_seconds:
            raise ValueError("walkoff_window_seconds must exceed active_window_seconds")
        self.active_window_seconds = int(active_window_seconds)
        self.walkoff_window_seconds = int(walkoff_window_seconds)
        self._clock = clock
        self._members: dict[str, ExpeditionMember] = {}
        self.revision = 0

    @staticmethod
    def normalize_actor_id(viewer_id: str | None, display_name: str) -> str:
        stable_id = str(viewer_id or "").strip()
        if stable_id:
            return f"twitch:{stable_id}"
        normalized_name = str(display_name).strip().casefold()
        if not normalized_name:
            raise ValueError("viewer identity is required")
        return f"twitch-name:{normalized_name}"

    def join(self, viewer_id: str | None, display_name: str) -> tuple[ExpeditionMember, bool]:
        now = self._clock()
        actor_id = self.normalize_actor_id(viewer_id, display_name)
        clean_name = str(display_name).strip()
        existing = self._members.get(actor_id)
        created = existing is None
        if existing is None:
            existing = ExpeditionMember(actor_id, clean_name, now, now)
            self._members[actor_id] = existing
        else:
            existing.display_name = clean_name or existing.display_name
            existing.last_seen_at = now
        self.revision += 1
        return existing, created

    def touch(self, viewer_id: str | None, display_name: str) -> bool:
        actor_id = self.normalize_actor_id(viewer_id, display_name)
        member = self._members.get(actor_id)
        if member is None:
            return False
        now = self._clock()
        changed = now != member.last_seen_at or (display_name and display_name != member.display_name)
        member.last_seen_at = now
        if display_name:
            member.display_name = str(display_name).strip()
        if changed:
            self.revision += 1
        return True

    def visible_members(self) -> list[dict]:
        now = self._clock()
        visible: list[dict] = []
        for member in self._members.values():
            age = max(0.0, now - member.last_seen_at)
            if age >= self.walkoff_window_seconds:
                continue
            visible.append(
                {
                    "actor_id": member.actor_id,
                    "display_name": member.display_name,
                    "class": member.character_class,
                    "presence": "active" if age < self.active_window_seconds else "idle",
                    "last_seen_at": member.last_seen_at,
                }
            )
        visible.sort(key=lambda item: (item["last_seen_at"], item["actor_id"]))
        return visible

    def snapshot(self) -> dict:
        return new_expedition_snapshot(
            self.visible_members(),
            active_window_seconds=self.active_window_seconds,
            walkoff_window_seconds=self.walkoff_window_seconds,
        )

    def joined_count(self) -> int:
        return len(self._members)
