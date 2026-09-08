"""MeanGene-owned persistent stream lore with deterministic retrieval."""

from __future__ import annotations

import re
import json
import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class LoreRecord:
    id: int
    subject: str
    subject_type: str
    category: str
    key: str
    value: str
    strength: int
    source: str
    enabled: bool
    created_at: str
    updated_at: str
    channel_scope: str = "global"
    canonical_statement: str = ""
    kind: str = "fact"
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    confidence: float = 0.5
    first_seen_at: str = ""
    last_seen_at: str = ""
    moderation_status: str = "APPROVED"
    moderated_at: Optional[str] = None
    moderator_discord_user_id: Optional[str] = None
    discord_message_id: Optional[str] = None


class LoreStore:
    """SQLite CRUD and bounded keyword retrieval for trusted internal callers."""

    _STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "by", "do", "does",
        "for", "from", "how", "i", "in", "is", "it", "me", "my", "of",
        "on", "or", "that", "the", "their", "this", "to", "was", "what",
        "when", "where", "who", "why", "with", "you", "your",
    }

    def __init__(self, path: str | Path = "data/lore.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lore (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL COLLATE NOCASE,
                    subject_type TEXT NOT NULL,
                    category TEXT NOT NULL COLLATE NOCASE,
                    key TEXT NOT NULL COLLATE NOCASE,
                    value TEXT NOT NULL,
                    strength INTEGER NOT NULL DEFAULT 50 CHECK(strength BETWEEN 0 AND 100),
                    source TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(subject, category, key, source)
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(lore)")}
            additions = {
                "channel_scope": "TEXT NOT NULL DEFAULT 'global'",
                "canonical_statement": "TEXT NOT NULL DEFAULT ''",
                "kind": "TEXT NOT NULL DEFAULT 'fact'",
                "aliases_json": "TEXT NOT NULL DEFAULT '[]'",
                "tags_json": "TEXT NOT NULL DEFAULT '[]'",
                "evidence_json": "TEXT NOT NULL DEFAULT '[]'",
                "confidence": "REAL NOT NULL DEFAULT 0.5",
                "first_seen_at": "TEXT NOT NULL DEFAULT ''",
                "last_seen_at": "TEXT NOT NULL DEFAULT ''",
                # SQLite cannot ADD this CHECK column to populated legacy tables on
                # supported runtimes; all writes below constrain the enum instead.
                "moderation_status": "TEXT NOT NULL DEFAULT 'APPROVED'",
                "moderated_at": "TEXT",
                "moderator_discord_user_id": "TEXT",
                "discord_message_id": "TEXT",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE lore ADD COLUMN {name} {declaration}")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS lore_schema (key TEXT PRIMARY KEY, version INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO lore_schema(key, version) VALUES ('schema', 3) "
                "ON CONFLICT(key) DO UPDATE SET version=excluded.version"
            )
            connection.execute(
                "UPDATE lore SET canonical_statement=value WHERE canonical_statement=''"
            )
            connection.execute(
                "UPDATE lore SET first_seen_at=created_at WHERE first_seen_at=''"
            )
            connection.execute(
                "UPDATE lore SET last_seen_at=updated_at WHERE last_seen_at=''"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lore_enabled_subject ON lore(enabled, subject)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lore_enabled_category ON lore(enabled, category)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lore_scope_enabled ON lore(channel_scope, enabled)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_lore_capture_identity "
                "ON lore(channel_scope, subject, kind, canonical_statement) "
                "WHERE source='capture'"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lore_active_scope "
                "ON lore(moderation_status, enabled, channel_scope)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_lore_discord_message "
                "ON lore(discord_message_id) WHERE discord_message_id IS NOT NULL"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _record(row: sqlite3.Row) -> LoreRecord:
        keys = set(row.keys())
        def array(name: str) -> tuple[str, ...]:
            try:
                value = json.loads(row[name]) if name in keys else []
                return tuple(str(item) for item in value) if isinstance(value, list) else ()
            except (TypeError, ValueError):
                return ()
        return LoreRecord(
            id=row["id"], subject=row["subject"], subject_type=row["subject_type"],
            category=row["category"], key=row["key"], value=row["value"],
            strength=row["strength"], source=row["source"], enabled=bool(row["enabled"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
            channel_scope=row["channel_scope"] if "channel_scope" in keys else "global",
            canonical_statement=(row["canonical_statement"] if "canonical_statement" in keys else row["value"]),
            kind=row["kind"] if "kind" in keys else "fact",
            aliases=array("aliases_json"), tags=array("tags_json"), evidence=array("evidence_json"),
            confidence=float(row["confidence"]) if "confidence" in keys else 0.5,
            first_seen_at=row["first_seen_at"] if "first_seen_at" in keys else row["created_at"],
            last_seen_at=row["last_seen_at"] if "last_seen_at" in keys else row["updated_at"],
            moderation_status=row["moderation_status"] if "moderation_status" in keys else "APPROVED",
            moderated_at=row["moderated_at"] if "moderated_at" in keys else None,
            moderator_discord_user_id=(row["moderator_discord_user_id"] if "moderator_discord_user_id" in keys else None),
            discord_message_id=row["discord_message_id"] if "discord_message_id" in keys else None,
        )

    def upsert_captured_lore(self, *, channel_scope: str, subject: str, kind: str,
                             statement: str, aliases: Iterable[str] = (),
                             tags: Iterable[str] = (), evidence: Iterable[str] = (),
                             confidence: float = 0.5, observed_at: Optional[str] = None,
                             rejected_suppression_seconds: float = 0) -> Optional[LoreRecord]:
        """Create one pending captured candidate, suppressing recent terminal duplicates."""
        record, _ = self.upsert_captured_lore_observed(
            channel_scope=channel_scope, subject=subject, kind=kind, statement=statement,
            aliases=aliases, tags=tags, evidence=evidence, confidence=confidence,
            observed_at=observed_at,
            rejected_suppression_seconds=rejected_suppression_seconds,
        )
        return record

    def upsert_captured_lore_observed(self, *, channel_scope: str, subject: str, kind: str,
                             statement: str, aliases: Iterable[str] = (),
                             tags: Iterable[str] = (), evidence: Iterable[str] = (),
                             confidence: float = 0.5, observed_at: Optional[str] = None,
                             rejected_suppression_seconds: float = 0) -> tuple[Optional[LoreRecord], str]:
        """Return the existing persistence result plus a finite observability outcome."""
        now = observed_at or self._now()
        scope, clean_subject = channel_scope.strip().casefold(), subject.strip()
        clean_kind = kind.strip().casefold()
        canonical = " ".join(statement.split())
        legacy_key = f"capture:{scope}:{clean_kind}:{hashlib.sha256(canonical.casefold().encode('utf-8')).hexdigest()[:24]}"
        alias_data = json.dumps(sorted(set(aliases), key=str.casefold), ensure_ascii=True)
        tag_data = json.dumps(sorted(set(tags), key=str.casefold), ensure_ascii=True)
        evidence_data = json.dumps(list(evidence), ensure_ascii=True)
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM lore WHERE channel_scope=? AND subject=? AND kind=? "
                "AND canonical_statement=? AND source='capture'",
                (scope, clean_subject, clean_kind, canonical),
            ).fetchone()
            if existing is not None:
                record = self._record(existing)
                # An extracted duplicate is never allowed to reopen or mutate
                # active lore. In particular, APPROVED rows retain their
                # enabled state and all moderation provenance.
                if record.moderation_status != "REJECTED":
                    return None, "duplicate"
                try:
                    rejected_at = datetime.fromisoformat((record.moderated_at or "").replace("Z", "+00:00"))
                    current = datetime.fromisoformat(now.replace("Z", "+00:00"))
                    if (current - rejected_at).total_seconds() < max(0, rejected_suppression_seconds):
                        return None, "rejected_cooldown"
                except (TypeError, ValueError):
                    return None, "rejected_cooldown"
                cursor = connection.execute(
                    """UPDATE lore SET value=?, strength=?, enabled=0, updated_at=?, aliases_json=?,
                       tags_json=?, evidence_json=?, confidence=?, last_seen_at=?, moderation_status='PENDING',
                       moderated_at=NULL, moderator_discord_user_id=NULL, discord_message_id=NULL
                       WHERE id=? AND moderation_status='REJECTED'""",
                    (canonical, round(max(0.0, min(1.0, float(confidence))) * 100), now,
                     alias_data, tag_data, evidence_data, max(0.0, min(1.0, float(confidence))),
                     now, record.id),
                )
                if cursor.rowcount != 1:
                    return None, "duplicate"
                row = connection.execute("SELECT * FROM lore WHERE id=?", (record.id,)).fetchone()
                return self._record(row), "stored"
            cursor = connection.execute(
                """INSERT INTO lore
                   (subject, subject_type, category, key, value, strength, source, enabled,
                    created_at, updated_at, channel_scope, canonical_statement, kind,
                    aliases_json, tags_json, evidence_json, confidence, first_seen_at, last_seen_at,
                    moderation_status)
                   VALUES (?, 'viewer', ?, ?, ?, ?, 'capture', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')""",
                (clean_subject, clean_kind, legacy_key, canonical,
                 round(max(0.0, min(1.0, float(confidence))) * 100), now, now, scope,
                 canonical, clean_kind, alias_data, tag_data, evidence_data,
                 max(0.0, min(1.0, float(confidence))), now, now),
            )
            row = connection.execute("SELECT * FROM lore WHERE id=?", (cursor.lastrowid,)).fetchone()
        if row is None:
            raise RuntimeError("Lore upsert did not return a record")
        return self._record(row), "stored"

    def correlate_discord_message(self, record_id: int, message_id: int) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE lore SET discord_message_id=? WHERE id=? AND moderation_status='PENDING' "
                "AND discord_message_id IS NULL",
                (str(message_id), record_id),
            )
        return cursor.rowcount == 1

    def moderate_pending(self, discord_message_id: int, decision: str, moderator_user_id: int) -> Optional[LoreRecord]:
        status = str(decision).upper()
        if status not in {"APPROVED", "REJECTED"}:
            return None
        now = self._now()
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE lore SET moderation_status=?, enabled=?, moderated_at=?,
                   moderator_discord_user_id=?, updated_at=?
                   WHERE discord_message_id=? AND moderation_status='PENDING'""",
                (status, int(status == "APPROVED"), now, str(moderator_user_id), now,
                 str(discord_message_id)),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT * FROM lore WHERE discord_message_id=?", (str(discord_message_id),)
            ).fetchone()
        return self._record(row) if row else None

    def add_lore(
        self,
        *,
        subject: str,
        subject_type: str,
        category: str,
        key: str,
        value: str,
        strength: int = 50,
        source: str = "operator",
        enabled: bool = True,
    ) -> LoreRecord:
        now = self._now()
        with self._connection() as connection:
            cursor = connection.execute(
                """INSERT INTO lore
                   (subject, subject_type, category, key, value, strength, source, enabled, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (subject.strip(), subject_type.strip(), category.strip(), key.strip(), value.strip(),
                 max(0, min(100, int(strength))), source.strip(), int(enabled), now, now),
            )
            record_id = cursor.lastrowid
        record = self.get_lore(record_id)
        if record is None:
            raise RuntimeError("Lore insert did not return a record")
        return record

    def update_lore(self, record_id: int, **changes) -> Optional[LoreRecord]:
        allowed = {"subject", "subject_type", "category", "key", "value", "strength", "source", "enabled"}
        updates = {name: value for name, value in changes.items() if name in allowed}
        if not updates:
            return self.get_lore(record_id)
        if "strength" in updates:
            updates["strength"] = max(0, min(100, int(updates["strength"])))
        if "enabled" in updates:
            updates["enabled"] = int(bool(updates["enabled"]))
        for name in {"subject", "subject_type", "category", "key", "value", "source"} & updates.keys():
            updates[name] = str(updates[name]).strip()
        updates["updated_at"] = self._now()
        assignments = ", ".join(f"{name} = ?" for name in updates)
        with self._connection() as connection:
            connection.execute(
                f"UPDATE lore SET {assignments} WHERE id = ?",
                (*updates.values(), record_id),
            )
        return self.get_lore(record_id)

    def disable_lore(self, record_id: int) -> Optional[LoreRecord]:
        return self.update_lore(record_id, enabled=False)

    def get_lore(self, record_id: int) -> Optional[LoreRecord]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM lore WHERE id = ?", (record_id,)).fetchone()
        return self._record(row) if row else None

    def seed_lore(self, records: Iterable[dict]) -> int:
        """Insert absent seed identities without overwriting operator edits."""
        inserted = 0
        for item in records:
            try:
                self.add_lore(**item)
                inserted += 1
            except sqlite3.IntegrityError:
                continue
        return inserted

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        return {
            token for token in re.findall(r"[a-z0-9_'-]{2,}", text.casefold())
            if token not in cls._STOPWORDS
        }

    @staticmethod
    def _mentioned(text: str, phrase: str) -> bool:
        normalized = phrase.casefold().strip().lstrip("@")
        return bool(normalized and re.search(rf"(?<![a-z0-9_])@?{re.escape(normalized)}(?![a-z0-9_])", text))

    def search_lore(self, query: str, limit: int = 6, channel_scope: Optional[str] = None) -> list[LoreRecord]:
        """Rank exact subjects/aliases first, then deterministic keyword overlap."""
        bounded_limit = max(1, min(8, int(limit)))
        normalized_query = query.casefold()
        query_tokens = self._tokens(query)
        with self._connection() as connection:
            if channel_scope:
                rows = connection.execute(
                    "SELECT * FROM lore WHERE enabled=1 AND moderation_status='APPROVED' AND channel_scope IN ('global', ?)",
                    (channel_scope.strip().casefold(),),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM lore WHERE enabled=1 AND moderation_status='APPROVED'"
                ).fetchall()
        records = [self._record(row) for row in rows]

        exact_subjects = {record.subject.casefold() for record in records if self._mentioned(normalized_query, record.subject)}
        alias_subjects = {
            record.subject.casefold()
            for record in records
            if record.category.casefold() == "alias" and self._mentioned(normalized_query, record.value)
        }
        ranked: list[tuple[int, int, int, LoreRecord]] = []
        for record in records:
            subject = record.subject.casefold()
            searchable = " ".join((record.subject, record.category, record.key, record.value,
                                    record.canonical_statement, *record.aliases, *record.tags))
            overlap = len(query_tokens & self._tokens(searchable))
            score = overlap * 10
            if subject in exact_subjects:
                score += 100
            elif subject in alias_subjects:
                score += 90
            if score:
                ranked.append((score, record.strength, -record.id, record))
        ranked.sort(reverse=True, key=lambda item: item[:3])
        return [item[3] for item in ranked[:bounded_limit]]


SAMPLE_LORE = (
    {
        "subject": "stream", "subject_type": "stream", "category": "running_gag",
        "key": "sample_gag", "value": "The sample victory bell is purely ceremonial.",
        "strength": 20, "source": "sample",
    },
    {
        "subject": "rpg_world", "subject_type": "world", "category": "rpg_lore",
        "key": "sample_tavern", "value": "The sample tavern is called The Copper Minnow.",
        "strength": 20, "source": "sample",
    },
)
