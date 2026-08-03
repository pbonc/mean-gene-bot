"""Persistent sold-vehicle exclusions and chat announcement queue."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


SOLD_FILE = Path(__file__).resolve().parents[1] / "data" / "wot_sold_vehicles.json"


def _read() -> dict[str, Any]:
    if not SOLD_FILE.is_file():
        return {"vehicles": {}, "pending": []}
    try:
        payload = json.loads(SOLD_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("vehicles", {})
            payload.setdefault("pending", [])
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {"vehicles": {}, "pending": []}


def _write(payload: dict[str, Any]) -> None:
    SOLD_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SOLD_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, SOLD_FILE)


def sold_vehicles() -> list[dict[str, Any]]:
    return sorted(
        _read()["vehicles"].values(),
        key=lambda vehicle: str(vehicle.get("name", "")).casefold(),
    )


def mark_sold(vehicle: dict[str, Any]) -> dict[str, Any]:
    tank_id = str(int(vehicle["tank_id"]))
    name = str(vehicle.get("name") or tank_id).strip()[:120]
    payload = _read()
    record = {
        "tank_id": int(tank_id),
        "name": name,
        "mode": str(vehicle.get("mode") or ""),
        "tier": vehicle.get("tier"),
        "era": vehicle.get("era"),
        "last_battle_time": vehicle.get("last_battle_time"),
        "marked_at": int(time.time()),
    }
    is_new = tank_id not in payload["vehicles"]
    payload["vehicles"][tank_id] = record
    if is_new:
        payload["pending"].append(
            {
                "tank_id": int(tank_id),
                "message": f"{name} set to sold status, removed from active inventory.",
            }
        )
    _write(payload)
    return record


def restore_vehicle(tank_id: int) -> bool:
    payload = _read()
    removed = payload["vehicles"].pop(str(int(tank_id)), None) is not None
    payload["pending"] = [
        item
        for item in payload["pending"]
        if int(item["tank_id"]) != int(tank_id)
    ]
    _write(payload)
    return removed


def pending_sold_announcements() -> list[dict[str, Any]]:
    return list(_read()["pending"])


def acknowledge_sold_announcement(tank_id: int) -> None:
    payload = _read()
    payload["pending"] = [
        item
        for item in payload["pending"]
        if int(item["tank_id"]) != int(tank_id)
    ]
    _write(payload)
