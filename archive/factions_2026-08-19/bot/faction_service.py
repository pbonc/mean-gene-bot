import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "factions.db")
DERPDAWG_RELIC_USER = "thederpdawg"


@dataclass
class Faction:
    id: int
    name: str
    normalized_name: str
    head_username: str
    influence: int
    member_count: int
    active_member_count: int
    owns_relic: bool
    created_at: str


class FactionService:
    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        max_factions: int = 5,
        switch_cooldown_days: int = 7,
        join_influence_bonus: int = 10,
    ):
        self.db_path = db_path
        self.max_factions = max_factions
        self.switch_cooldown_days = switch_cooldown_days
        self.join_influence_bonus = join_influence_bonus
        self._initialize_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize_schema(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS factions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    head_username TEXT NOT NULL UNIQUE,
                    influence INTEGER NOT NULL DEFAULT 0,
                    owns_relic INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faction_members (
                    user_username TEXT PRIMARY KEY,
                    faction_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    FOREIGN KEY (faction_id) REFERENCES factions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_faction_state (
                    user_username TEXT PRIMARY KEY,
                    last_faction_change_at TEXT
                )
                """
            )
            # Backward-compatible migration: leave cooldown now uses last_leave_at.
            # Keep last_faction_change_at for legacy compatibility.
            user_state_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(user_faction_state)").fetchall()
            }
            if "last_leave_at" not in user_state_columns:
                conn.execute("ALTER TABLE user_faction_state ADD COLUMN last_leave_at TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commissioner_state (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    username TEXT,
                    faction_id INTEGER,
                    assigned_at TEXT,
                    assigned_by TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faction_member_activity (
                    user_username TEXT PRIMARY KEY,
                    faction_id INTEGER NOT NULL,
                    last_meaningful_chat_at TEXT NOT NULL,
                    FOREIGN KEY (faction_id) REFERENCES factions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faction_member_stream_activity (
                    user_username TEXT NOT NULL,
                    faction_id INTEGER NOT NULL,
                    stream_session_id INTEGER NOT NULL,
                    rewarded_at TEXT NOT NULL,
                    PRIMARY KEY (user_username, stream_session_id),
                    FOREIGN KEY (faction_id) REFERENCES factions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faction_echo_trigger_state (
                    user_username TEXT NOT NULL,
                    stream_session_id INTEGER NOT NULL,
                    triggered_at TEXT NOT NULL,
                    PRIMARY KEY (user_username, stream_session_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_chat_state (
                    user_username TEXT PRIMARY KEY,
                    last_reward_at TEXT,
                    last_message_norm TEXT,
                    last_message_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_session_state (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    current_session_id INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relics (
                    relic_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    owner_faction_id INTEGER,
                    defense_bonus INTEGER NOT NULL DEFAULT 20,
                    influence_bonus INTEGER NOT NULL DEFAULT 0,
                    stream_start_bonus INTEGER NOT NULL DEFAULT 1,
                    announcement_flavor TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    updated_by TEXT,
                    FOREIGN KEY (owner_faction_id) REFERENCES factions(id) ON DELETE SET NULL
                )
                """
            )
            # Backward-compatible migration: old derpdawg relic id is now derp.
            has_derp = conn.execute(
                "SELECT 1 FROM relics WHERE relic_id = 'derp' LIMIT 1"
            ).fetchone()
            has_derpdawg = conn.execute(
                "SELECT 1 FROM relics WHERE relic_id = 'derpdawg' LIMIT 1"
            ).fetchone()
            if not has_derp and has_derpdawg:
                conn.execute(
                    """
                    UPDATE relics
                    SET relic_id = 'derp',
                        display_name = 'Derp',
                        announcement_flavor = 'Derp ensures 1-entry stream actions pay at least 2 before relic multipliers.'
                    WHERE relic_id = 'derpdawg'
                    """
                )
            elif has_derp and has_derpdawg:
                conn.execute("DELETE FROM relics WHERE relic_id = 'derpdawg'")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faction_surge_state (
                    faction_id INTEGER PRIMARY KEY,
                    last_triggered_at TEXT,
                    last_stream_session_id INTEGER,
                    last_triggered_by TEXT,
                    FOREIGN KEY (faction_id) REFERENCES factions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faction_surge_member_state (
                    user_username TEXT NOT NULL,
                    stream_session_id INTEGER NOT NULL,
                    reward_count INTEGER NOT NULL DEFAULT 0,
                    last_rewarded_at TEXT,
                    PRIMARY KEY (user_username, stream_session_id)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO stream_session_state (singleton_id, current_session_id)
                VALUES (1, 0)
                ON CONFLICT(singleton_id) DO NOTHING
                """
            )
            now_iso = self._now_iso()
            conn.execute(
                """
                INSERT INTO relics (
                    relic_id,
                    display_name,
                    owner_faction_id,
                    defense_bonus,
                    influence_bonus,
                    stream_start_bonus,
                    announcement_flavor,
                    is_active,
                    updated_at,
                    updated_by
                )
                VALUES (?, ?, NULL, ?, 0, 1, ?, 1, ?, NULL)
                ON CONFLICT(relic_id) DO NOTHING
                """,
                (
                    "gmb",
                    "Golden Milkbone",
                    20,
                    "The Golden Milkbone amplifies incoming raffle rewards.",
                    now_iso,
                ),
            )
            conn.execute(
                """
                INSERT INTO relics (
                    relic_id,
                    display_name,
                    owner_faction_id,
                    defense_bonus,
                    influence_bonus,
                    stream_start_bonus,
                    announcement_flavor,
                    is_active,
                    updated_at,
                    updated_by
                )
                VALUES (?, ?, NULL, ?, 0, 0, ?, 1, ?, NULL)
                ON CONFLICT(relic_id) DO NOTHING
                """,
                (
                    "derp",
                    "Derp",
                    20,
                    "Derp ensures 1-entry stream actions pay at least 2 before relic multipliers.",
                    now_iso,
                ),
            )
            conn.execute(
                """
                INSERT INTO commissioner_state (singleton_id, username, faction_id, assigned_at, assigned_by)
                VALUES (1, NULL, NULL, NULL, NULL)
                ON CONFLICT(singleton_id) DO NOTHING
                """
            )

    def get_relic(self, relic_id: str) -> Optional[dict]:
        relic_id = str(relic_id or "").strip().lower()
        if not relic_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT relic_id, display_name, owner_faction_id, defense_bonus, influence_bonus,
                       stream_start_bonus, announcement_flavor, is_active, updated_at, updated_by
                FROM relics
                WHERE relic_id = ?
                """,
                (relic_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "relic_id": row["relic_id"],
                "display_name": row["display_name"],
                "owner_faction_id": row["owner_faction_id"],
                "defense_bonus": int(row["defense_bonus"] or 0),
                "influence_bonus": int(row["influence_bonus"] or 0),
                "stream_start_bonus": int(row["stream_start_bonus"] or 0),
                "announcement_flavor": row["announcement_flavor"],
                "is_active": bool(row["is_active"]),
                "updated_at": row["updated_at"],
                "updated_by": row["updated_by"],
            }

    def faction_owns_relic(self, faction_id: int, relic_id: str = "gmb") -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM relics
                WHERE relic_id = ?
                  AND is_active = 1
                  AND owner_faction_id = ?
                LIMIT 1
                """,
                (str(relic_id).strip().lower(), faction_id),
            ).fetchone()
            return bool(row)

    def neutralize_relic(self, relic_id: str, acted_by: Optional[str] = None) -> tuple[bool, str]:
        relic_id = str(relic_id or "").strip().lower()
        if not relic_id:
            return False, "Relic id is required."

        acted_by_norm = self._normalize_username(acted_by) if acted_by else None
        now_iso = self._now_iso()
        with self._connect() as conn:
            relic = conn.execute(
                """
                SELECT relic_id, display_name, owner_faction_id
                FROM relics
                WHERE relic_id = ?
                """,
                (relic_id,),
            ).fetchone()
            if not relic:
                return False, f"Relic '{relic_id}' not found."

            conn.execute(
                """
                UPDATE relics
                SET owner_faction_id = NULL,
                    updated_at = ?,
                    updated_by = ?
                WHERE relic_id = ?
                """,
                (now_iso, acted_by_norm, relic_id),
            )

            if relic_id == "gmb":
                conn.execute("UPDATE factions SET owns_relic = 0")

            return True, f"{relic['display_name']} is now neutral."

    def set_relic_owner(self, relic_id: str, faction_id: int, acted_by: Optional[str] = None) -> tuple[bool, str]:
        relic_id = str(relic_id or "").strip().lower()
        if not relic_id:
            return False, "Relic id is required."

        acted_by_norm = self._normalize_username(acted_by) if acted_by else None
        now_iso = self._now_iso()
        with self._connect() as conn:
            relic = conn.execute(
                """
                SELECT relic_id, display_name
                FROM relics
                WHERE relic_id = ? AND is_active = 1
                """,
                (relic_id,),
            ).fetchone()
            if not relic:
                return False, f"Relic '{relic_id}' not found or inactive."

            faction = conn.execute(
                """
                SELECT id, name
                FROM factions
                WHERE id = ? AND is_active = 1
                """,
                (faction_id,),
            ).fetchone()
            if not faction:
                return False, "Target faction not found."

            conn.execute(
                """
                UPDATE relics
                SET owner_faction_id = ?,
                    updated_at = ?,
                    updated_by = ?
                WHERE relic_id = ?
                """,
                (faction_id, now_iso, acted_by_norm, relic_id),
            )

            if relic_id == "gmb":
                conn.execute("UPDATE factions SET owns_relic = CASE WHEN id = ? THEN 1 ELSE 0 END", (faction_id,))

            return True, f"{faction['name']} now controls {relic['display_name']}."

    def get_faction_surge_cooldown_remaining(self, faction_id: int, cooldown_minutes: int) -> timedelta:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT last_triggered_at
                FROM faction_surge_state
                WHERE faction_id = ?
                """,
                (faction_id,),
            ).fetchone()

        if not row or not row["last_triggered_at"]:
            return timedelta(0)

        try:
            last_triggered = datetime.fromisoformat(row["last_triggered_at"])
        except ValueError:
            return timedelta(0)

        elapsed = datetime.now(timezone.utc) - last_triggered
        cooldown = timedelta(minutes=cooldown_minutes)
        remaining = cooldown - elapsed
        return remaining if remaining > timedelta(0) else timedelta(0)

    def mark_faction_surge_trigger(self, faction_id: int, stream_session_id: int, triggered_by: str):
        triggered_by = self._normalize_username(triggered_by)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO faction_surge_state (faction_id, last_triggered_at, last_stream_session_id, last_triggered_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(faction_id) DO UPDATE SET
                    last_triggered_at = excluded.last_triggered_at,
                    last_stream_session_id = excluded.last_stream_session_id,
                    last_triggered_by = excluded.last_triggered_by
                """,
                (faction_id, self._now_iso(), stream_session_id, triggered_by),
            )

    def get_user_surge_reward_count(self, username: str, stream_session_id: int) -> int:
        username = self._normalize_username(username)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT reward_count
                FROM faction_surge_member_state
                WHERE user_username = ? AND stream_session_id = ?
                """,
                (username, stream_session_id),
            ).fetchone()
            return int(row["reward_count"]) if row else 0

    def increment_user_surge_reward_count(self, username: str, stream_session_id: int):
        username = self._normalize_username(username)
        now_iso = self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO faction_surge_member_state (user_username, stream_session_id, reward_count, last_rewarded_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_username, stream_session_id) DO UPDATE SET
                    reward_count = reward_count + 1,
                    last_rewarded_at = excluded.last_rewarded_at
                """,
                (username, stream_session_id, now_iso),
            )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_username(username: str) -> str:
        return username.lstrip("@").strip().lower()

    @staticmethod
    def _normalize_faction_name(name: str) -> str:
        return " ".join(name.strip().split()).lower()

    @staticmethod
    def _iso_to_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _get_faction_by_id(self, conn: sqlite3.Connection, faction_id: int) -> Optional[sqlite3.Row]:
        return conn.execute(
            """
             SELECT f.id, f.name, f.normalized_name, f.head_username, f.influence,
                 CASE WHEN rg.owner_faction_id = f.id THEN 1 ELSE 0 END AS owns_relic,
                 f.created_at,
                   COUNT(m.user_username) AS member_count
            FROM factions f
             LEFT JOIN relics rg ON rg.relic_id = 'gmb' AND rg.is_active = 1
            LEFT JOIN faction_members m ON m.faction_id = f.id
            WHERE f.id = ? AND f.is_active = 1
            GROUP BY f.id
            """,
            (faction_id,),
        ).fetchone()

    def _get_faction_by_normalized_name(self, conn: sqlite3.Connection, normalized_name: str) -> Optional[sqlite3.Row]:
        return conn.execute(
            """
             SELECT f.id, f.name, f.normalized_name, f.head_username, f.influence,
                 CASE WHEN rg.owner_faction_id = f.id THEN 1 ELSE 0 END AS owns_relic,
                 f.created_at,
                   COUNT(m.user_username) AS member_count
            FROM factions f
             LEFT JOIN relics rg ON rg.relic_id = 'gmb' AND rg.is_active = 1
            LEFT JOIN faction_members m ON m.faction_id = f.id
            WHERE f.normalized_name = ? AND f.is_active = 1
            GROUP BY f.id
            """,
            (normalized_name,),
        ).fetchone()

    def list_factions(self) -> list[Faction]:
        current_session_id = self.get_current_stream_session_id()
        with self._connect() as conn:
            rows = conn.execute(
                """
                  SELECT f.id, f.name, f.normalized_name, f.head_username, f.influence,
                      CASE WHEN rg.owner_faction_id = f.id THEN 1 ELSE 0 END AS owns_relic,
                      f.created_at,
                       COUNT(m.user_username) AS member_count,
                       COALESCE(SUM(CASE WHEN s.stream_session_id = ? THEN 1 ELSE 0 END), 0) AS active_member_count
                FROM factions f
                  LEFT JOIN relics rg ON rg.relic_id = 'gmb' AND rg.is_active = 1
                LEFT JOIN faction_members m ON m.faction_id = f.id
                LEFT JOIN faction_member_stream_activity s
                    ON s.user_username = m.user_username
                    AND s.faction_id = f.id
                    AND s.stream_session_id = ?
                WHERE f.is_active = 1
                GROUP BY f.id
                ORDER BY f.influence DESC, f.name ASC
                """,
                (current_session_id, current_session_id),
            ).fetchall()

        return [
            Faction(
                id=row["id"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                head_username=row["head_username"],
                influence=row["influence"],
                member_count=row["member_count"],
                active_member_count=row["active_member_count"],
                owns_relic=bool(row["owns_relic"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_faction_by_id(self, faction_id: int) -> Optional[Faction]:
        with self._connect() as conn:
            row = self._get_faction_by_id(conn, faction_id)
            if not row:
                return None
            return Faction(
                id=row["id"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                head_username=row["head_username"],
                influence=row["influence"],
                member_count=row["member_count"],
                active_member_count=0,
                owns_relic=bool(row["owns_relic"]),
                created_at=row["created_at"],
            )

    def get_faction_by_name(self, faction_name: str) -> Optional[Faction]:
        normalized_name = self._normalize_faction_name(faction_name)
        with self._connect() as conn:
            row = self._get_faction_by_normalized_name(conn, normalized_name)
            if not row:
                return None
            return Faction(
                id=row["id"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                head_username=row["head_username"],
                influence=row["influence"],
                member_count=row["member_count"],
                active_member_count=0,
                owns_relic=bool(row["owns_relic"]),
                created_at=row["created_at"],
            )

    def get_user_faction(self, username: str) -> Optional[Faction]:
        username = self._normalize_username(username)
        with self._connect() as conn:
            row = conn.execute(
                """
                  SELECT f.id, f.name, f.normalized_name, f.head_username, f.influence,
                      CASE WHEN rg.owner_faction_id = f.id THEN 1 ELSE 0 END AS owns_relic,
                      f.created_at,
                       COUNT(m2.user_username) AS member_count
                FROM faction_members m
                JOIN factions f ON f.id = m.faction_id AND f.is_active = 1
                  LEFT JOIN relics rg ON rg.relic_id = 'gmb' AND rg.is_active = 1
                LEFT JOIN faction_members m2 ON m2.faction_id = f.id
                WHERE m.user_username = ?
                GROUP BY f.id
                """,
                (username,),
            ).fetchone()

            if not row:
                return None

            return Faction(
                id=row["id"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                head_username=row["head_username"],
                influence=row["influence"],
                member_count=row["member_count"],
                active_member_count=0,
                owns_relic=bool(row["owns_relic"]),
                created_at=row["created_at"],
            )

    def get_chat_state(self, username: str) -> dict:
        username = self._normalize_username(username)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT last_reward_at, last_message_norm, last_message_at
                FROM user_chat_state
                WHERE user_username = ?
                """,
                (username,),
            ).fetchone()

        if not row:
            return {
                "last_reward_at": None,
                "last_message_norm": None,
                "last_message_at": None,
            }

        return {
            "last_reward_at": self._iso_to_dt(row["last_reward_at"]),
            "last_message_norm": row["last_message_norm"],
            "last_message_at": self._iso_to_dt(row["last_message_at"]),
        }

    def get_current_stream_session_id(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT current_session_id FROM stream_session_state WHERE singleton_id = 1"
            ).fetchone()
            if not row:
                return 0
            return int(row["current_session_id"])

    def ensure_stream_session_started(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT current_session_id FROM stream_session_state WHERE singleton_id = 1"
            ).fetchone()
            current = int(row["current_session_id"]) if row else 0
            if current > 0:
                return current

            # Always allocate a fresh session id so historical per-session
            # activity and echo-trigger data are never reused.
            max_activity = conn.execute(
                "SELECT COALESCE(MAX(stream_session_id), 0) AS max_id FROM faction_member_stream_activity"
            ).fetchone()["max_id"]
            max_echo = conn.execute(
                "SELECT COALESCE(MAX(stream_session_id), 0) AS max_id FROM faction_echo_trigger_state"
            ).fetchone()["max_id"]
            next_session = max(max_activity, max_echo) + 1

            conn.execute(
                "UPDATE stream_session_state SET current_session_id = ? WHERE singleton_id = 1",
                (next_session,),
            )
            return next_session

    def start_new_stream_session(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT current_session_id FROM stream_session_state WHERE singleton_id = 1"
            ).fetchone()
            current = int(row["current_session_id"]) if row else 0

            max_activity = conn.execute(
                "SELECT COALESCE(MAX(stream_session_id), 0) AS max_id FROM faction_member_stream_activity"
            ).fetchone()["max_id"]
            max_echo = conn.execute(
                "SELECT COALESCE(MAX(stream_session_id), 0) AS max_id FROM faction_echo_trigger_state"
            ).fetchone()["max_id"]
            max_known = max(current, max_activity, max_echo)
            next_session = max_known + 1

            conn.execute(
                "UPDATE stream_session_state SET current_session_id = ? WHERE singleton_id = 1",
                (next_session,),
            )
            return next_session

    def end_current_stream_session(self):
        """Mark stream activity tracking as inactive until the next stream starts."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE stream_session_state SET current_session_id = 0 WHERE singleton_id = 1"
            )

    def reset_activity_for_current_stream_session(self) -> tuple[bool, str]:
        """Clear per-session faction activity markers for the active stream session.

        This resets active-member counts and per-session trigger/cap tracking
        without modifying faction membership, influence, or cooldown history.
        """
        session_id = self.get_current_stream_session_id()
        if session_id <= 0:
            return False, "No active stream session to reset."

        with self._connect() as conn:
            conn.execute(
                "DELETE FROM faction_member_stream_activity WHERE stream_session_id = ?",
                (session_id,),
            )
            conn.execute(
                "DELETE FROM faction_echo_trigger_state WHERE stream_session_id = ?",
                (session_id,),
            )
            conn.execute(
                "DELETE FROM faction_surge_member_state WHERE stream_session_id = ?",
                (session_id,),
            )

        return True, "Faction activity status reset for current stream session."

    def get_active_members_for_current_session(self) -> list[str]:
        session_id = self.get_current_stream_session_id()
        if session_id <= 0:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_username
                FROM faction_member_stream_activity
                WHERE stream_session_id = ?
                ORDER BY rewarded_at ASC
                """,
                (session_id,),
            ).fetchall()
            return [str(row["user_username"]).lower() for row in rows]

    def get_recent_active_members(self, window_minutes: int = 20) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.user_username
                FROM faction_member_activity a
                JOIN faction_members m ON m.user_username = a.user_username AND m.faction_id = a.faction_id
                JOIN factions f ON f.id = m.faction_id AND f.is_active = 1
                WHERE a.last_meaningful_chat_at >= ?
                ORDER BY a.last_meaningful_chat_at DESC
                """,
                (cutoff.isoformat(),),
            ).fetchall()
            return [str(row["user_username"]).lower() for row in rows]

    def has_stream_activity_for_current_session(self, username: str) -> bool:
        username = self._normalize_username(username)
        session_id = self.get_current_stream_session_id()
        if session_id <= 0:
            return False

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM faction_member_stream_activity
                WHERE user_username = ? AND stream_session_id = ?
                LIMIT 1
                """,
                (username, session_id),
            ).fetchone()
            return bool(row)

    def get_active_members_for_faction_current_session(self, faction_id: int) -> list[str]:
        session_id = self.get_current_stream_session_id()
        if session_id <= 0:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_username
                FROM faction_member_stream_activity
                WHERE faction_id = ? AND stream_session_id = ?
                ORDER BY rewarded_at ASC
                """,
                (faction_id, session_id),
            ).fetchall()
            return [str(row["user_username"]).lower() for row in rows]

    def get_recent_active_members_for_faction(self, faction_id: int, window_minutes: int = 20) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.user_username
                FROM faction_member_activity a
                JOIN faction_members m ON m.user_username = a.user_username AND m.faction_id = a.faction_id
                JOIN factions f ON f.id = m.faction_id AND f.is_active = 1
                WHERE a.faction_id = ?
                  AND a.last_meaningful_chat_at >= ?
                ORDER BY a.last_meaningful_chat_at DESC
                """,
                (faction_id, cutoff.isoformat()),
            ).fetchall()
            return [str(row["user_username"]).lower() for row in rows]

    def is_user_active_member(self, username: str, window_minutes: int = 20) -> bool:
        username = self._normalize_username(username)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM faction_member_activity a
                JOIN faction_members m ON m.user_username = a.user_username AND m.faction_id = a.faction_id
                JOIN factions f ON f.id = m.faction_id AND f.is_active = 1
                WHERE a.user_username = ?
                  AND a.last_meaningful_chat_at >= ?
                LIMIT 1
                """,
                (username, cutoff.isoformat()),
            ).fetchone()
            return bool(row)

    def try_mark_echo_triggered_for_current_session(self, username: str) -> bool:
        """Return True only once per user per stream session."""
        username = self._normalize_username(username)
        session_id = self.get_current_stream_session_id()
        if session_id <= 0:
            return False

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO faction_echo_trigger_state (user_username, stream_session_id, triggered_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_username, stream_session_id) DO NOTHING
                """,
                (username, session_id, self._now_iso()),
            )
            return cur.rowcount > 0

    def update_chat_state(
        self,
        username: str,
        *,
        last_reward_at: Optional[datetime],
        last_message_norm: str,
        last_message_at: datetime,
    ):
        username = self._normalize_username(username)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_chat_state (user_username, last_reward_at, last_message_norm, last_message_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_username) DO UPDATE SET
                    last_reward_at = excluded.last_reward_at,
                    last_message_norm = excluded.last_message_norm,
                    last_message_at = excluded.last_message_at
                """,
                (
                    username,
                    last_reward_at.isoformat() if last_reward_at else None,
                    last_message_norm,
                    last_message_at.isoformat(),
                ),
            )

    def clear_chat_reward_cooldown(self, username: str):
        username = self._normalize_username(username)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_chat_state (user_username, last_reward_at, last_message_norm, last_message_at)
                VALUES (?, NULL, NULL, NULL)
                ON CONFLICT(user_username) DO UPDATE SET
                    last_reward_at = NULL,
                    last_message_norm = NULL,
                    last_message_at = NULL
                """,
                (username,),
            )

    def apply_meaningful_chat_reward(self, username: str, influence_amount: int = 1) -> Optional[str]:
        username = self._normalize_username(username)
        now_iso = self._now_iso()
        session_id = self.ensure_stream_session_started()
        with self._connect() as conn:
            membership = conn.execute(
                """
                SELECT f.id AS faction_id, f.name AS faction_name
                FROM faction_members m
                JOIN factions f ON f.id = m.faction_id AND f.is_active = 1
                WHERE m.user_username = ?
                """,
                (username,),
            ).fetchone()

            if not membership:
                return None

            faction_id = membership["faction_id"]
            conn.execute(
                "UPDATE factions SET influence = influence + ? WHERE id = ?",
                (influence_amount, faction_id),
            )
            conn.execute(
                """
                INSERT INTO faction_member_activity (user_username, faction_id, last_meaningful_chat_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_username) DO UPDATE SET
                    faction_id = excluded.faction_id,
                    last_meaningful_chat_at = excluded.last_meaningful_chat_at
                """,
                (username, faction_id, now_iso),
            )
            conn.execute(
                """
                INSERT INTO faction_member_stream_activity (user_username, faction_id, stream_session_id, rewarded_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_username, stream_session_id) DO UPDATE SET
                    faction_id = excluded.faction_id,
                    rewarded_at = excluded.rewarded_at
                """,
                (username, faction_id, session_id, now_iso),
            )

            return membership["faction_name"]

    def add_influence_for_user_faction(self, username: str, influence_amount: int = 1) -> Optional[Faction]:
        username = self._normalize_username(username)
        with self._connect() as conn:
            membership = conn.execute(
                """
                  SELECT f.id, f.name, f.normalized_name, f.head_username, f.influence,
                      CASE WHEN rg.owner_faction_id = f.id THEN 1 ELSE 0 END AS owns_relic,
                      f.created_at,
                       COUNT(m2.user_username) AS member_count
                FROM faction_members m
                JOIN factions f ON f.id = m.faction_id AND f.is_active = 1
                  LEFT JOIN relics rg ON rg.relic_id = 'gmb' AND rg.is_active = 1
                LEFT JOIN faction_members m2 ON m2.faction_id = f.id
                WHERE m.user_username = ?
                GROUP BY f.id
                """,
                (username,),
            ).fetchone()

            if not membership:
                return None

            conn.execute(
                "UPDATE factions SET influence = influence + ? WHERE id = ?",
                (influence_amount, membership["id"]),
            )

            updated = self._get_faction_by_id(conn, int(membership["id"]))
            if not updated:
                return None

            return Faction(
                id=updated["id"],
                name=updated["name"],
                normalized_name=updated["normalized_name"],
                head_username=updated["head_username"],
                influence=updated["influence"],
                member_count=updated["member_count"],
                active_member_count=0,
                owns_relic=bool(updated["owns_relic"]),
                created_at=updated["created_at"],
            )

    def add_influence_for_faction(self, faction_id: int, influence_amount: int = 1) -> Optional[Faction]:
        with self._connect() as conn:
            faction = self._get_faction_by_id(conn, faction_id)
            if not faction:
                return None

            conn.execute(
                "UPDATE factions SET influence = influence + ? WHERE id = ?",
                (influence_amount, faction_id),
            )

            updated = self._get_faction_by_id(conn, faction_id)
            if not updated:
                return None

            return Faction(
                id=updated["id"],
                name=updated["name"],
                normalized_name=updated["normalized_name"],
                head_username=updated["head_username"],
                influence=updated["influence"],
                member_count=updated["member_count"],
                active_member_count=0,
                owns_relic=bool(updated["owns_relic"]),
                created_at=updated["created_at"],
            )

    def get_cooldown_remaining(self, username: str) -> timedelta:
        # Legacy alias retained for callers; cooldown now refers to leave cooldown.
        return self.get_leave_cooldown_remaining(username)

    def get_leave_cooldown_remaining(self, username: str) -> timedelta:
        username = self._normalize_username(username)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_leave_at FROM user_faction_state WHERE user_username = ?",
                (username,),
            ).fetchone()
            if not row or not row["last_leave_at"]:
                return timedelta(0)
            try:
                last_change = datetime.fromisoformat(row["last_leave_at"])
            except ValueError:
                return timedelta(0)

        elapsed = datetime.now(timezone.utc) - last_change
        cooldown = timedelta(days=self.switch_cooldown_days)
        remaining = cooldown - elapsed
        return remaining if remaining > timedelta(0) else timedelta(0)

    def _set_last_change(self, conn: sqlite3.Connection, username: str):
        # Legacy helper retained for compatibility.
        conn.execute(
            """
            INSERT INTO user_faction_state (user_username, last_faction_change_at)
            VALUES (?, ?)
            ON CONFLICT(user_username) DO UPDATE SET last_faction_change_at = excluded.last_faction_change_at
            """,
            (username, self._now_iso()),
        )

    def _set_last_leave(self, conn: sqlite3.Connection, username: str):
        conn.execute(
            """
            INSERT INTO user_faction_state (user_username, last_faction_change_at, last_leave_at)
            VALUES (?, NULL, ?)
            ON CONFLICT(user_username) DO UPDATE SET last_leave_at = excluded.last_leave_at
            """,
            (username, self._now_iso()),
        )

    def create_faction(self, faction_name: str, head_username: str) -> tuple[bool, str]:
        head_username = self._normalize_username(head_username)
        normalized_name = self._normalize_faction_name(faction_name)
        display_name = " ".join(faction_name.strip().split())

        if not display_name:
            return False, "Faction name cannot be empty."
        if display_name.isdigit():
            return False, "Faction name cannot be numeric-only."

        with self._connect() as conn:
            active_count = conn.execute(
                "SELECT COUNT(*) AS c FROM factions WHERE is_active = 1"
            ).fetchone()["c"]
            if active_count >= self.max_factions:
                return False, f"Maximum of {self.max_factions} active factions reached."

            existing_name = self._get_faction_by_normalized_name(conn, normalized_name)
            if existing_name:
                return False, "A faction with that name already exists."

            existing_head = conn.execute(
                "SELECT id FROM factions WHERE head_username = ? AND is_active = 1",
                (head_username,),
            ).fetchone()
            if existing_head:
                return False, f"@{head_username} is already a faction head."

            existing_member = conn.execute(
                "SELECT faction_id FROM faction_members WHERE user_username = ?",
                (head_username,),
            ).fetchone()
            if existing_member:
                return False, f"@{head_username} is already in a faction."

            now = self._now_iso()
            cur = conn.execute(
                """
                INSERT INTO factions (name, normalized_name, head_username, influence, owns_relic, created_at, is_active)
                VALUES (?, ?, ?, 0, 0, ?, 1)
                """,
                (display_name, normalized_name, head_username, now),
            )
            faction_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO faction_members (user_username, faction_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (head_username, faction_id, now),
            )

        return True, f"Faction '{display_name}' created with head @{head_username}."

    def disband_faction(self, faction_name: str) -> tuple[bool, str]:
        normalized_name = self._normalize_faction_name(faction_name)
        with self._connect() as conn:
            faction = self._get_faction_by_normalized_name(conn, normalized_name)
            if not faction:
                return False, "Faction not found."

            member_rows = conn.execute(
                "SELECT user_username FROM faction_members WHERE faction_id = ?",
                (faction["id"],),
            ).fetchall()

            conn.execute("DELETE FROM faction_members WHERE faction_id = ?", (faction["id"],))
            conn.execute("DELETE FROM faction_member_activity WHERE faction_id = ?", (faction["id"],))
            conn.execute("UPDATE factions SET is_active = 0, owns_relic = 0 WHERE id = ?", (faction["id"],))
            conn.execute(
                """
                UPDATE relics
                SET owner_faction_id = NULL,
                    updated_at = ?,
                    updated_by = ?
                WHERE owner_faction_id = ?
                """,
                (self._now_iso(), "system:disband", faction["id"]),
            )

            commissioner = conn.execute(
                "SELECT faction_id FROM commissioner_state WHERE singleton_id = 1"
            ).fetchone()
            if commissioner and commissioner["faction_id"] == faction["id"]:
                conn.execute(
                    """
                    UPDATE commissioner_state
                    SET username = NULL, faction_id = NULL, assigned_at = NULL, assigned_by = NULL
                    WHERE singleton_id = 1
                    """
                )

        return True, f"Faction '{faction['name']}' has been disbanded."

    def join_faction(self, username: str, faction_id: int) -> tuple[bool, str]:
        username = self._normalize_username(username)

        if username == DERPDAWG_RELIC_USER:
            return False, "@thederpdawg is a relic-bound participant and cannot join factions manually."

        with self._connect() as conn:
            faction = self._get_faction_by_id(conn, faction_id)
            if not faction:
                return False, "Faction not found."

            current_membership = conn.execute(
                "SELECT faction_id FROM faction_members WHERE user_username = ?",
                (username,),
            ).fetchone()
            if current_membership:
                if current_membership["faction_id"] == faction_id:
                    return False, f"You are already in {faction['name']}."
                return False, "You are already in another faction. Use !faction leave first."

            now = self._now_iso()
            conn.execute(
                "INSERT INTO faction_members (user_username, faction_id, joined_at) VALUES (?, ?, ?)",
                (username, faction_id, now),
            )
            conn.execute("DELETE FROM faction_member_activity WHERE user_username = ?", (username,))
            conn.execute(
                "UPDATE factions SET influence = influence + ? WHERE id = ?",
                (self.join_influence_bonus, faction_id),
            )

            faction_name = faction["name"]

        # Ensure first meaningful chat after joining can earn activity rewards.
        self.clear_chat_reward_cooldown(username)

        return True, f"@{username} joined {faction_name}!"

    def leave_faction(self, username: str) -> tuple[bool, str]:
        username = self._normalize_username(username)

        if username == DERPDAWG_RELIC_USER:
            return False, "@thederpdawg is a relic-bound participant and cannot leave factions manually."

        remaining = self.get_leave_cooldown_remaining(username)
        if remaining > timedelta(0):
            hours = max(1, int(remaining.total_seconds() // 3600))
            return False, f"Leave cooldown active. You can leave again in about {hours}h."

        with self._connect() as conn:
            membership = conn.execute(
                """
                SELECT f.id, f.name
                FROM faction_members m
                JOIN factions f ON f.id = m.faction_id
                WHERE m.user_username = ? AND f.is_active = 1
                """,
                (username,),
            ).fetchone()
            if not membership:
                return False, "You are not currently in a faction."

            conn.execute("DELETE FROM faction_members WHERE user_username = ?", (username,))
            conn.execute("DELETE FROM faction_member_activity WHERE user_username = ?", (username,))
            self._set_last_leave(conn, username)
            return True, f"@{username} left {membership['name']}."

    def get_commissioner(self) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username, faction_id, assigned_at, assigned_by
                FROM commissioner_state
                WHERE singleton_id = 1
                """
            ).fetchone()
            if not row or not row["username"]:
                return None
            return {
                "username": row["username"],
                "faction_id": row["faction_id"],
                "assigned_at": row["assigned_at"],
                "assigned_by": row["assigned_by"],
            }

    def set_commissioner(self, username: str, assigned_by: str) -> tuple[bool, str]:
        username = self._normalize_username(username)
        assigned_by = self._normalize_username(assigned_by)

        with self._connect() as conn:
            faction = conn.execute(
                "SELECT id, name FROM factions WHERE head_username = ? AND is_active = 1",
                (username,),
            ).fetchone()
            if not faction:
                return False, "Commissioner must be an active faction head."

            conn.execute(
                """
                UPDATE commissioner_state
                SET username = ?, faction_id = ?, assigned_at = ?, assigned_by = ?
                WHERE singleton_id = 1
                """,
                (username, faction["id"], self._now_iso(), assigned_by),
            )
            return True, f"@{username} has been appointed Stream Commissioner."

    def clear_commissioner(self, cleared_by: str) -> tuple[bool, str]:
        cleared_by = self._normalize_username(cleared_by)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE commissioner_state
                SET username = NULL, faction_id = NULL, assigned_at = ?, assigned_by = ?
                WHERE singleton_id = 1
                """,
                (self._now_iso(), cleared_by),
            )
        return True, "Commissioner position is now vacant."
