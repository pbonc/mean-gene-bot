"""Durable first-battle inventory detection for WoTWoM."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from bot.wot_api import fetch_wot_inventory


SNAPSHOT_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "wot_inventory_snapshot.json"
)
_snapshot_lock = asyncio.Lock()


def _read_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_FILE.is_file():
        return {}
    try:
        payload = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_snapshot(payload: dict[str, Any]) -> None:
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, SNAPSHOT_FILE)


def snapshot_status() -> dict[str, Any]:
    snapshot = _read_snapshot()
    return {
        "initialized": bool(snapshot.get("initialized_at")),
        "vehicle_count": len(snapshot.get("vehicles") or {}),
        "pending_count": len(snapshot.get("pending") or []),
        "initialized_at": snapshot.get("initialized_at"),
        "updated_at": snapshot.get("updated_at"),
        "nickname": snapshot.get("nickname"),
        "last_error": snapshot.get("last_error"),
    }


async def refresh_wot_snapshot() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Refresh played vehicles and durably queue IDs first observed after baseline."""
    async with _snapshot_lock:
        now = int(time.time())
        previous = _read_snapshot()
        inventory = await fetch_wot_inventory()
        vehicles = {
            str(vehicle["tank_id"]): vehicle for vehicle in inventory["vehicles"]
        }

        if not previous.get("initialized_at"):
            snapshot = {
                "version": 1,
                "account_id": inventory["account_id"],
                "nickname": inventory["nickname"],
                "source": inventory["source"],
                "initialized_at": now,
                "updated_at": now,
                "vehicles": vehicles,
                "pending": [],
                "last_error": None,
            }
            _write_snapshot(snapshot)
            return inventory, []

        previous_ids = set((previous.get("vehicles") or {}).keys())
        discovered = [
            vehicle
            for tank_id, vehicle in vehicles.items()
            if tank_id not in previous_ids
        ]
        pending_by_id = {
            str(vehicle["tank_id"]): vehicle
            for vehicle in (previous.get("pending") or [])
        }
        for vehicle in discovered:
            pending_by_id[str(vehicle["tank_id"])] = vehicle

        previous.update(
            {
                "version": 1,
                "account_id": inventory["account_id"],
                "nickname": inventory["nickname"],
                "source": inventory["source"],
                "updated_at": now,
                "vehicles": vehicles,
                "pending": list(pending_by_id.values()),
                "last_error": None,
            }
        )
        _write_snapshot(previous)
        return inventory, discovered


def pending_deliveries() -> list[dict[str, Any]]:
    return list(_read_snapshot().get("pending") or [])


async def acknowledge_delivery(tank_id: int) -> None:
    async with _snapshot_lock:
        snapshot = _read_snapshot()
        snapshot["pending"] = [
            vehicle
            for vehicle in (snapshot.get("pending") or [])
            if int(vehicle["tank_id"]) != int(tank_id)
        ]
        _write_snapshot(snapshot)


async def record_refresh_error(message: str) -> None:
    async with _snapshot_lock:
        snapshot = _read_snapshot()
        if snapshot:
            snapshot["last_error"] = message
            snapshot["updated_at"] = int(time.time())
            _write_snapshot(snapshot)
