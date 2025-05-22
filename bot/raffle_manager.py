import json
import os
import random
from datetime import datetime
from typing import List, Dict, Optional

DEFAULT_STATE = {
    "raffle_active": False,
    "daily_entry_amount": 1,
    "raffle_id": None,
    "persistent_grants": {},
    "number_to_user": {},
    "raffle_locked": False,
    "mommadar_awarded": False
}

class RaffleManager:
    def __init__(self, filename: str):
        self.filename = filename
        self.state = {}
        self.daily_entries = {}
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.state = DEFAULT_STATE.copy()
        else:
            self.state = DEFAULT_STATE.copy()
            self.save()

        # Ensure all required keys exist
        for key, default in DEFAULT_STATE.items():
            self.state.setdefault(key, default)

        self.daily_entries = {}

    def save(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def clear_daily_entries(self):
        self.daily_entries = {}

    def clear_sheet(self):
        """Explicitly clear all picked numbers."""
        self.state["number_to_user"] = {}
        self.save()

    def open_raffle(self, entry_amount: int, raffle_id: str):
        # Only update fields needed for a new raffle — no destructive overwrite
        self.state["raffle_active"] = True
        self.state["daily_entry_amount"] = entry_amount
        self.state["raffle_id"] = raffle_id
        self.state["raffle_locked"] = False
        self.state["mommadar_awarded"] = False
        self.clear_daily_entries()
        self.save()

    def close_raffle(self):
        self.state["raffle_active"] = False
        self.clear_daily_entries()
        self.save()

    def grant_daily_entry(self, username: str):
        if not self.state["raffle_active"]:
            return False
        if username not in self.daily_entries:
            self.daily_entries[username] = self.state["daily_entry_amount"]
            return True
        return False

    def grant_persistent_entries(self, username: str, count: int):
        user_data = self.state["persistent_grants"].setdefault(username, {"total": 0, "redeemed": 0})
        user_data["total"] += count
        self.save()

    def available_entries(self, username: str) -> int:
        daily = self.daily_entries.get(username, 0)
        persistent = self.state["persistent_grants"].get(username, {"total": 0, "redeemed": 0})
        return daily + (persistent["total"] - persistent["redeemed"])

    def redeem_entries(self, username: str, numbers: List[str]) -> bool:
        if len(numbers) > self.available_entries(username):
            return False
        for number in numbers:
            if number in self.state["number_to_user"]:
                return False

        for number in numbers:
            self.state["number_to_user"][number] = username
            if self.daily_entries.get(username, 0) > 0:
                self.daily_entries[username] -= 1
            else:
                self.state["persistent_grants"][username]["redeemed"] += 1

        self.save()
        return True

    def draw_winner(self) -> Optional[str]:
        if not self.state["number_to_user"]:
            return None
        number = random.choice(list(self.state["number_to_user"].keys()))
        winner = self.state["number_to_user"][number]
        return f"🎉 Winner: {winner} with number {number}"

    def get_user_numbers(self, username: str) -> List[str]:
        return [number for number, user in self.state["number_to_user"].items() if user == username]

    def get_summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for user in self.state["number_to_user"].values():
            counts[user] = counts.get(user, 0) + 1
        return counts
