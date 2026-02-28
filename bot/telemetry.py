import json
import os
import threading
from datetime import datetime
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_TELEMETRY_FILE = os.path.join(_LOG_DIR, "telemetry.jsonl")
_TELEMETRY_LOCK = threading.Lock()
_TELEMETRY_FULL_JSON = os.getenv("TELEMETRY_FULL_JSON", "false").strip().lower() == "true"


def _utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def log_event(event_type: str, payload: dict[str, Any] | None = None):
    payload = payload or {}
    record = {
        "ts": _utc_iso(),
        "event_type": str(event_type),
        **payload,
    }
    line = _safe_json_dumps(record)
    with _TELEMETRY_LOCK:
        with open(_TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def summarize_rpg_state(state: dict[str, Any]) -> dict[str, Any]:
    users = state.get("users", {}) if isinstance(state, dict) else {}
    session = state.get("session", {}) if isinstance(state, dict) else {}
    monsters = session.get("monsters", []) if isinstance(session, dict) else []
    participants = session.get("participants", []) if isinstance(session, dict) else []
    action_queue = session.get("action_queue", []) if isinstance(session, dict) else []
    alive_monsters = sum(1 for m in monsters if isinstance(m, dict) and m.get("alive"))

    summary: dict[str, Any] = {
        "users_count": len(users) if isinstance(users, dict) else 0,
        "battle_active": bool(session.get("battle_active")) if isinstance(session, dict) else False,
        "phase": session.get("phase") if isinstance(session, dict) else None,
        "turn_number": int(session.get("turn_number", 0)) if isinstance(session, dict) else 0,
        "participants_count": len(participants) if isinstance(participants, list) else 0,
        "action_queue_count": len(action_queue) if isinstance(action_queue, list) else 0,
        "monsters_count": len(monsters) if isinstance(monsters, list) else 0,
        "alive_monsters_count": alive_monsters,
    }

    if _TELEMETRY_FULL_JSON:
        summary["state"] = state

    return summary


def summarize_rpg_log(log_data: dict[str, Any]) -> dict[str, Any]:
    daily_log = log_data.get("daily_log", []) if isinstance(log_data, dict) else []
    battle_log = log_data.get("battle_log", []) if isinstance(log_data, dict) else []

    summary: dict[str, Any] = {
        "daily_log_count": len(daily_log) if isinstance(daily_log, list) else 0,
        "battle_log_count": len(battle_log) if isinstance(battle_log, list) else 0,
        "battle_id": log_data.get("battle_id") if isinstance(log_data, dict) else None,
    }

    if _TELEMETRY_FULL_JSON:
        summary["log"] = log_data

    return summary


def tail_events(limit: int = 25, event_type: str | None = None) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if not os.path.exists(_TELEMETRY_FILE):
        return []

    with _TELEMETRY_LOCK:
        with open(_TELEMETRY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    output: list[dict[str, Any]] = []
    wanted_type = event_type.strip().lower() if event_type else None

    for raw_line in reversed(lines):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            item = json.loads(raw_line)
        except Exception:
            continue

        if wanted_type and str(item.get("event_type", "")).lower() != wanted_type:
            continue

        output.append(item)
        if len(output) >= limit:
            break

    output.reverse()
    return output


def telemetry_file_path() -> str:
    return _TELEMETRY_FILE
