"""Durable WoTWoM operation result tracking."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


RESULTS_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "wot_operation_results.json"
)


def _read() -> list[dict[str, Any]]:
    if not RESULTS_FILE.is_file():
        return []
    try:
        payload = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write(results: list[dict[str, Any]]) -> None:
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = RESULTS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(results, indent=2), encoding="utf-8")
    os.replace(temporary, RESULTS_FILE)


def record_operation(payload: dict[str, Any]) -> dict[str, Any]:
    agent = str(payload.get("agent") or "").strip().lstrip("@")[:40]
    outcome = str(payload.get("outcome") or "").strip().lower()
    if not agent:
        raise ValueError("An agent must be confirmed before signing.")
    if outcome not in {"pass", "fail"}:
        raise ValueError("Select pass or fail before signing.")
    orders = payload.get("orders") if isinstance(payload.get("orders"), dict) else {}
    result = {
        "agent": agent,
        "agent_key": agent.casefold(),
        "outcome": outcome,
        "orders": {
            key: str(orders.get(key) or "")[:120]
            for key in ("mode", "class", "tank", "challenge")
        },
        "signed_by": "Dar",
        "created_at": int(time.time()),
    }
    results = _read()
    results.append(result)
    _write(results)
    return result


def operation_stats() -> dict[str, Any]:
    results = _read()
    agents: dict[str, dict[str, Any]] = {}
    for result in results:
        key = str(result.get("agent_key") or result.get("agent", "")).casefold()
        if not key:
            continue
        entry = agents.setdefault(
            key,
            {"agent": result.get("agent") or key, "pass": 0, "fail": 0},
        )
        outcome = result.get("outcome")
        if outcome in {"pass", "fail"}:
            entry[outcome] += 1
    most_pass = max(agents.values(), key=lambda item: item["pass"], default=None)
    most_fail = max(agents.values(), key=lambda item: item["fail"], default=None)
    return {
        "total": len(results),
        "agents": agents,
        "most_pass": most_pass,
        "most_fail": most_fail,
    }
